"""Servicio de vuelos: reserva y cancela cupos. Dueño de la tabla `reservas_vuelo`.

Las dos operaciones son idempotentes: repetir la misma petición (por ejemplo,
por un reintento de la SAGA) no reserva ni devuelve cupos dos veces.
"""

import os
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

app = FastAPI(title="Servicio de vuelos")


def conexion() -> psycopg.Connection:
    # El bloque `with` confirma la transacción al salir bien y la revierte si hay error.
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], prepare_threshold=None, row_factory=dict_row)


class SolicitudReserva(BaseModel):
    orden_id: UUID
    vuelo_id: UUID
    pasajeros: int = Field(default=1, gt=0)
    simular_fallo: bool = False  # lo activa la SAGA para demostrar las compensaciones


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/reservas", status_code=201)
def reservar(solicitud: SolicitudReserva, response: Response) -> dict:
    if solicitud.simular_fallo:
        raise HTTPException(status_code=503, detail="Fallo simulado en el servicio de vuelos")

    with conexion() as con:
        existente = con.execute(
            "select * from reservas_vuelo where orden_id = %s", (solicitud.orden_id,)
        ).fetchone()
        if existente:
            if existente["estado"] == "CANCELADA":
                raise HTTPException(status_code=409, detail="La reserva de esta orden ya fue cancelada")
            response.status_code = 200  # ya estaba hecha: se devuelve la misma
            return existente

        # Descuenta solo si alcanzan los cupos; la condición y la resta ocurren en una
        # sola sentencia, así dos reservas simultáneas no pueden vender el mismo cupo.
        descontado = con.execute(
            "update vuelos set cupos_disponibles = cupos_disponibles - %(n)s "
            "where id = %(id)s and cupos_disponibles >= %(n)s returning id",
            {"n": solicitud.pasajeros, "id": solicitud.vuelo_id},
        ).fetchone()
        if descontado is None:
            existe = con.execute("select 1 from vuelos where id = %s", (solicitud.vuelo_id,)).fetchone()
            if not existe:
                raise HTTPException(status_code=404, detail="El vuelo no existe")
            raise HTTPException(status_code=409, detail="No hay cupos suficientes en el vuelo")

        return con.execute(
            "insert into reservas_vuelo (orden_id, vuelo_id, pasajeros, estado) "
            "values (%s, %s, %s, 'RESERVADA') returning *",
            (solicitud.orden_id, solicitud.vuelo_id, solicitud.pasajeros),
        ).fetchone()


@app.post("/reservas/{orden_id}/cancelar")
def cancelar(orden_id: UUID) -> dict:
    """Compensación de la SAGA: libera los cupos de la orden."""
    with conexion() as con:
        cancelada = con.execute(
            "update reservas_vuelo set estado = 'CANCELADA', actualizado_en = now() "
            "where orden_id = %s and estado = 'RESERVADA' returning *",
            (orden_id,),
        ).fetchone()
        if cancelada is None:
            # Ya estaba cancelada o nunca se reservó: compensar igual debe salir bien.
            existente = con.execute("select * from reservas_vuelo where orden_id = %s", (orden_id,)).fetchone()
            return existente or {"orden_id": orden_id, "estado": "SIN_RESERVA"}

        con.execute(
            "update vuelos set cupos_disponibles = cupos_disponibles + %s where id = %s",
            (cancelada["pasajeros"], cancelada["vuelo_id"]),
        )
        return cancelada


@app.get("/reservas/{orden_id}")
def consultar(orden_id: UUID) -> dict:
    with conexion() as con:
        reserva = con.execute("select * from reservas_vuelo where orden_id = %s", (orden_id,)).fetchone()
    if reserva is None:
        raise HTTPException(status_code=404, detail="No hay reserva de vuelo para esta orden")
    return reserva
