"""Servicio de autos: reserva y cancela vehículos. Dueño de la tabla `reservas_auto`.

Las dos operaciones son idempotentes: repetir la misma petición (por ejemplo,
por un reintento de la SAGA) no reserva ni devuelve unidades dos veces.
"""

import os
from datetime import date
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, model_validator

app = FastAPI(title="Servicio de autos")


def conexion() -> psycopg.Connection:
    # El bloque `with` confirma la transacción al salir bien y la revierte si hay error.
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], prepare_threshold=None, row_factory=dict_row)


class SolicitudReserva(BaseModel):
    orden_id: UUID
    auto_id: UUID
    fecha_recogida: date
    fecha_devolucion: date
    simular_fallo: bool = False  # lo activa la SAGA para demostrar las compensaciones

    @model_validator(mode="after")
    def fechas_en_orden(self):
        if self.fecha_devolucion <= self.fecha_recogida:
            raise ValueError("La fecha de devolución debe ser posterior a la de recogida")
        return self


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/reservas", status_code=201)
def reservar(solicitud: SolicitudReserva, response: Response) -> dict:
    if solicitud.simular_fallo:
        raise HTTPException(status_code=503, detail="Fallo simulado en el servicio de autos")

    with conexion() as con:
        existente = con.execute(
            "select * from reservas_auto where orden_id = %s", (solicitud.orden_id,)
        ).fetchone()
        if existente:
            if existente["estado"] == "CANCELADA":
                raise HTTPException(status_code=409, detail="La reserva de esta orden ya fue cancelada")
            response.status_code = 200  # ya estaba hecha: se devuelve la misma
            return existente

        # Un auto por orden. La condición y la resta van en una sola sentencia,
        # así dos reservas simultáneas no pueden tomar la misma unidad.
        descontado = con.execute(
            "update autos set unidades_disponibles = unidades_disponibles - 1 "
            "where id = %s and unidades_disponibles >= 1 returning id",
            (solicitud.auto_id,),
        ).fetchone()
        if descontado is None:
            existe = con.execute("select 1 from autos where id = %s", (solicitud.auto_id,)).fetchone()
            if not existe:
                raise HTTPException(status_code=404, detail="El auto no existe")
            raise HTTPException(status_code=409, detail="No hay unidades disponibles de este auto")

        return con.execute(
            "insert into reservas_auto (orden_id, auto_id, fecha_recogida, fecha_devolucion, estado) "
            "values (%s, %s, %s, %s, 'RESERVADA') returning *",
            (solicitud.orden_id, solicitud.auto_id, solicitud.fecha_recogida, solicitud.fecha_devolucion),
        ).fetchone()


@app.post("/reservas/{orden_id}/cancelar")
def cancelar(orden_id: UUID) -> dict:
    """Compensación de la SAGA: libera el auto de la orden."""
    with conexion() as con:
        cancelada = con.execute(
            "update reservas_auto set estado = 'CANCELADA', actualizado_en = now() "
            "where orden_id = %s and estado = 'RESERVADA' returning *",
            (orden_id,),
        ).fetchone()
        if cancelada is None:
            # Ya estaba cancelada o nunca se reservó: compensar igual debe salir bien.
            existente = con.execute("select * from reservas_auto where orden_id = %s", (orden_id,)).fetchone()
            return existente or {"orden_id": orden_id, "estado": "SIN_RESERVA"}

        con.execute(
            "update autos set unidades_disponibles = unidades_disponibles + 1 where id = %s",
            (cancelada["auto_id"],),
        )
        return cancelada


@app.get("/reservas/{orden_id}")
def consultar(orden_id: UUID) -> dict:
    with conexion() as con:
        reserva = con.execute("select * from reservas_auto where orden_id = %s", (orden_id,)).fetchone()
    if reserva is None:
        raise HTTPException(status_code=404, detail="No hay reserva de auto para esta orden")
    return reserva
