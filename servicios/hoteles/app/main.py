"""Servicio de hoteles: reserva y cancela habitaciones. Dueño de la tabla `reservas_hotel`.

Las dos operaciones son idempotentes: repetir la misma petición (por ejemplo,
por un reintento de la SAGA) no reserva ni devuelve habitaciones dos veces.
"""

import os
from datetime import date
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, model_validator

app = FastAPI(title="Servicio de hoteles")


def conexion() -> psycopg.Connection:
    # El bloque `with` confirma la transacción al salir bien y la revierte si hay error.
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], prepare_threshold=None, row_factory=dict_row)


class SolicitudReserva(BaseModel):
    orden_id: UUID
    hotel_id: UUID
    fecha_entrada: date
    fecha_salida: date
    simular_fallo: bool = False  # lo activa la SAGA para demostrar las compensaciones

    @model_validator(mode="after")
    def fechas_en_orden(self):
        if self.fecha_salida <= self.fecha_entrada:
            raise ValueError("La fecha de salida debe ser posterior a la de entrada")
        return self


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/reservas", status_code=201)
def reservar(solicitud: SolicitudReserva, response: Response) -> dict:
    if solicitud.simular_fallo:
        raise HTTPException(status_code=503, detail="Fallo simulado en el servicio de hoteles")

    with conexion() as con:
        existente = con.execute(
            "select * from reservas_hotel where orden_id = %s", (solicitud.orden_id,)
        ).fetchone()
        if existente:
            if existente["estado"] == "CANCELADA":
                raise HTTPException(status_code=409, detail="La reserva de esta orden ya fue cancelada")
            response.status_code = 200  # ya estaba hecha: se devuelve la misma
            return existente

        # Una habitación por orden. La condición y la resta van en una sola sentencia,
        # así dos reservas simultáneas no pueden tomar la misma habitación.
        descontado = con.execute(
            "update hoteles set habitaciones_disponibles = habitaciones_disponibles - 1 "
            "where id = %s and habitaciones_disponibles >= 1 returning id",
            (solicitud.hotel_id,),
        ).fetchone()
        if descontado is None:
            existe = con.execute("select 1 from hoteles where id = %s", (solicitud.hotel_id,)).fetchone()
            if not existe:
                raise HTTPException(status_code=404, detail="El hotel no existe")
            raise HTTPException(status_code=409, detail="No hay habitaciones disponibles en el hotel")

        return con.execute(
            "insert into reservas_hotel (orden_id, hotel_id, fecha_entrada, fecha_salida, estado) "
            "values (%s, %s, %s, %s, 'RESERVADA') returning *",
            (solicitud.orden_id, solicitud.hotel_id, solicitud.fecha_entrada, solicitud.fecha_salida),
        ).fetchone()


@app.post("/reservas/{orden_id}/cancelar")
def cancelar(orden_id: UUID) -> dict:
    """Compensación de la SAGA: libera la habitación de la orden."""
    with conexion() as con:
        cancelada = con.execute(
            "update reservas_hotel set estado = 'CANCELADA', actualizado_en = now() "
            "where orden_id = %s and estado = 'RESERVADA' returning *",
            (orden_id,),
        ).fetchone()
        if cancelada is None:
            # Ya estaba cancelada o nunca se reservó: compensar igual debe salir bien.
            existente = con.execute("select * from reservas_hotel where orden_id = %s", (orden_id,)).fetchone()
            return existente or {"orden_id": orden_id, "estado": "SIN_RESERVA"}

        con.execute(
            "update hoteles set habitaciones_disponibles = habitaciones_disponibles + 1 where id = %s",
            (cancelada["hotel_id"],),
        )
        return cancelada


@app.get("/reservas/{orden_id}")
def consultar(orden_id: UUID) -> dict:
    with conexion() as con:
        reserva = con.execute("select * from reservas_hotel where orden_id = %s", (orden_id,)).fetchone()
    if reserva is None:
        raise HTTPException(status_code=404, detail="No hay reserva de hotel para esta orden")
    return reserva
