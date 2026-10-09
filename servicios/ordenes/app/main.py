"""Servicio de órdenes y facturación. Dueño de `ordenes`, `pagos` y `saga_pasos`.

Crea la orden en estado PENDIENTE y le pide a Prefect que ejecute la SAGA. El
flow de la SAGA vuelve a llamar a este servicio para cobrar, reembolsar,
cambiar el estado de la orden y dejar la bitácora de pasos.
"""

import os
from datetime import date
from typing import Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

PREFECT_API_URL = os.environ.get("PREFECT_API_URL", "http://prefect-server:4200/api")
DEPLOYMENT_SAGA = "saga-reserva/orquestada"

# estado nuevo -> estados desde los que se puede llegar
TRANSICIONES = {
    "CONFIRMADA": ["PENDIENTE"],
    "COMPENSANDO": ["PENDIENTE"],
    "CANCELADA": ["COMPENSANDO"],
}

app = FastAPI(title="Servicio de órdenes y facturación")


def conexion() -> psycopg.Connection:
    # El bloque `with` confirma la transacción al salir bien y la revierte si hay error.
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], prepare_threshold=None, row_factory=dict_row)


class SolicitudOrden(BaseModel):
    usuario_id: UUID
    vuelo_id: UUID
    hotel_id: UUID
    auto_id: UUID
    fecha_inicio: date
    fecha_fin: date
    pasajeros: int = Field(default=1, gt=0)
    clave_idempotencia: UUID
    simular_fallo_en: Literal["VUELO", "HOTEL", "AUTO", "PAGO"] | None = None

    @model_validator(mode="after")
    def fechas_en_orden(self):
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio")
        return self


class SolicitudPago(BaseModel):
    simular_fallo: bool = False


class CambioEstado(BaseModel):
    estado: Literal["CONFIRMADA", "COMPENSANDO", "CANCELADA"]
    motivo_fallo: str | None = None


class PasoSaga(BaseModel):
    paso: Literal["VUELO", "HOTEL", "AUTO", "PAGO"]
    tipo: Literal["ACCION", "COMPENSACION"]
    estado: Literal["OK", "FALLO"]
    detalle: str | None = None


def _calcular_total(con: psycopg.Connection, s: SolicitudOrden) -> int:
    precios = con.execute(
        "select (select precio_cop from vuelos where id = %s) as vuelo, "
        "(select precio_noche_cop from hoteles where id = %s) as hotel, "
        "(select precio_dia_cop from autos where id = %s) as auto",
        (s.vuelo_id, s.hotel_id, s.auto_id),
    ).fetchone()
    faltantes = [nombre for nombre, precio in precios.items() if precio is None]
    if faltantes:
        raise HTTPException(status_code=404, detail=f"No existe en el catálogo: {', '.join(faltantes)}")
    noches = (s.fecha_fin - s.fecha_inicio).days
    return precios["vuelo"] * s.pasajeros + precios["hotel"] * noches + precios["auto"] * noches


def _lanzar_saga(orden_id: UUID) -> str:
    """Pide a Prefect una ejecución del flow de la SAGA para esta orden."""
    with httpx.Client(base_url=PREFECT_API_URL, timeout=15) as prefect:
        deployment = prefect.get(f"/deployments/name/{DEPLOYMENT_SAGA}")
        deployment.raise_for_status()
        ejecucion = prefect.post(
            f"/deployments/{deployment.json()['id']}/create_flow_run",
            json={"parameters": {"orden_id": str(orden_id)}},
        )
        ejecucion.raise_for_status()
        return ejecucion.json()["id"]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ordenes", status_code=201)
def crear_orden(solicitud: SolicitudOrden, response: Response) -> dict:
    with conexion() as con:
        existente = con.execute(
            "select * from ordenes where clave_idempotencia = %s", (solicitud.clave_idempotencia,)
        ).fetchone()
        if existente:
            response.status_code = 200  # doble envío: se devuelve la orden original
            return existente

        orden = con.execute(
            "insert into ordenes (usuario_id, vuelo_id, hotel_id, auto_id, fecha_inicio, fecha_fin, "
            "pasajeros, total_cop, simular_fallo_en, clave_idempotencia) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (solicitud.usuario_id, solicitud.vuelo_id, solicitud.hotel_id, solicitud.auto_id,
             solicitud.fecha_inicio, solicitud.fecha_fin, solicitud.pasajeros,
             _calcular_total(con, solicitud), solicitud.simular_fallo_en, solicitud.clave_idempotencia),
        ).fetchone()

    # La orden ya quedó guardada; ahora se lanza la SAGA fuera de esa transacción.
    try:
        flow_run_id = _lanzar_saga(orden["id"])
    except httpx.HTTPError as error:
        with conexion() as con:
            con.execute(
                "update ordenes set estado = 'CANCELADA', motivo_fallo = %s, actualizado_en = now() where id = %s",
                ("No se pudo iniciar la SAGA en Prefect", orden["id"]),
            )
        raise HTTPException(status_code=503, detail="No se pudo iniciar la SAGA en Prefect") from error

    with conexion() as con:
        return con.execute(
            "update ordenes set flow_run_id = %s where id = %s returning *", (flow_run_id, orden["id"])
        ).fetchone()


@app.get("/ordenes")
def listar_ordenes(usuario_id: UUID) -> list[dict]:
    with conexion() as con:
        return con.execute(
            "select * from ordenes where usuario_id = %s order by creado_en desc", (usuario_id,)
        ).fetchall()


@app.get("/ordenes/{orden_id}")
def consultar_orden(orden_id: UUID) -> dict:
    with conexion() as con:
        orden = con.execute("select * from ordenes where id = %s", (orden_id,)).fetchone()
        if orden is None:
            raise HTTPException(status_code=404, detail="La orden no existe")
        orden["pago"] = con.execute("select * from pagos where orden_id = %s", (orden_id,)).fetchone()
        orden["pasos"] = con.execute(
            "select paso, tipo, estado, detalle, creado_en from saga_pasos where orden_id = %s order by id",
            (orden_id,),
        ).fetchall()
    return orden


# ----- Rutas que usa el flow de la SAGA -----

@app.post("/ordenes/{orden_id}/pago", status_code=201)
def cobrar(orden_id: UUID, response: Response, solicitud: SolicitudPago = SolicitudPago()) -> dict:
    if solicitud.simular_fallo:
        raise HTTPException(status_code=503, detail="Fallo simulado en la pasarela de pagos")

    with conexion() as con:
        existente = con.execute("select * from pagos where orden_id = %s", (orden_id,)).fetchone()
        if existente:
            if existente["estado"] == "REEMBOLSADO":
                raise HTTPException(status_code=409, detail="El pago de esta orden ya fue reembolsado")
            response.status_code = 200  # ya estaba cobrado: no se cobra dos veces
            return existente

        pago = con.execute(
            "insert into pagos (orden_id, monto_cop, estado) "
            "select id, total_cop, 'COBRADO' from ordenes where id = %s returning *",
            (orden_id,),
        ).fetchone()
        if pago is None:
            raise HTTPException(status_code=404, detail="La orden no existe")
        return pago


@app.post("/ordenes/{orden_id}/pago/reembolsar")
def reembolsar(orden_id: UUID) -> dict:
    """Compensación de la SAGA: devuelve el cobro de la orden."""
    with conexion() as con:
        reembolsado = con.execute(
            "update pagos set estado = 'REEMBOLSADO', actualizado_en = now() "
            "where orden_id = %s and estado = 'COBRADO' returning *",
            (orden_id,),
        ).fetchone()
        if reembolsado is None:
            # Ya estaba reembolsado o nunca se cobró: compensar igual debe salir bien.
            existente = con.execute("select * from pagos where orden_id = %s", (orden_id,)).fetchone()
            return existente or {"orden_id": orden_id, "estado": "SIN_PAGO"}
        return reembolsado


@app.post("/ordenes/{orden_id}/estado")
def cambiar_estado(orden_id: UUID, cambio: CambioEstado) -> dict:
    with conexion() as con:
        orden = con.execute(
            "update ordenes set estado = %s, motivo_fallo = coalesce(%s, motivo_fallo), actualizado_en = now() "
            "where id = %s and (estado = any(%s) or estado = %s) returning *",
            (cambio.estado, cambio.motivo_fallo, orden_id, TRANSICIONES[cambio.estado], cambio.estado),
        ).fetchone()
        if orden is None:
            existe = con.execute("select estado from ordenes where id = %s", (orden_id,)).fetchone()
            if existe is None:
                raise HTTPException(status_code=404, detail="La orden no existe")
            raise HTTPException(
                status_code=409, detail=f"No se puede pasar de {existe['estado']} a {cambio.estado}"
            )
        return orden


@app.post("/ordenes/{orden_id}/pasos", status_code=201)
def registrar_paso(orden_id: UUID, paso: PasoSaga) -> dict:
    with conexion() as con:
        return con.execute(
            "insert into saga_pasos (orden_id, paso, tipo, estado, detalle) "
            "values (%s, %s, %s, %s, %s) returning *",
            (orden_id, paso.paso, paso.tipo, paso.estado, paso.detalle),
        ).fetchone()
