"""Guardado del catálogo en Supabase (PostgreSQL).

Cada sentencia es un "upsert": inserta el registro o, si ya existe según la
clave única de la tabla, actualiza precio y datos. El inventario (cupos,
habitaciones, unidades) no se toca al actualizar: lo administran las reservas.
"""

import os

import psycopg

_UPSERT = {
    "vuelos": """
        insert into vuelos (origen, destino, fecha_salida, hora_salida, hora_llegada,
                            aerolinea, duracion_min, escalas, precio_cop, fuente)
        values (%(origen)s, %(destino)s, %(fecha_salida)s, %(hora_salida)s, %(hora_llegada)s,
                %(aerolinea)s, %(duracion_min)s, %(escalas)s, %(precio_cop)s, %(fuente)s)
        on conflict (origen, destino, fecha_salida, aerolinea, hora_salida) do update set
            hora_llegada = excluded.hora_llegada,
            duracion_min = excluded.duracion_min,
            escalas      = excluded.escalas,
            precio_cop   = excluded.precio_cop,
            fuente       = excluded.fuente,
            extraido_en  = now()
    """,
    "hoteles": """
        insert into hoteles (nombre, ciudad, estrellas, puntuacion, precio_noche_cop, servicios, fuente)
        values (%(nombre)s, %(ciudad)s, %(estrellas)s, %(puntuacion)s, %(precio_noche_cop)s,
                %(servicios)s, %(fuente)s)
        on conflict (nombre, ciudad) do update set
            estrellas        = excluded.estrellas,
            puntuacion       = excluded.puntuacion,
            precio_noche_cop = excluded.precio_noche_cop,
            servicios        = excluded.servicios,
            fuente           = excluded.fuente,
            extraido_en      = now()
    """,
    "autos": """
        insert into autos (ciudad, proveedor, modelo, categoria, precio_dia_cop, fuente)
        values (%(ciudad)s, %(proveedor)s, %(modelo)s, %(categoria)s, %(precio_dia_cop)s, %(fuente)s)
        on conflict (ciudad, proveedor, modelo) do update set
            categoria      = excluded.categoria,
            precio_dia_cop = excluded.precio_dia_cop,
            fuente         = excluded.fuente,
            extraido_en    = now()
    """,
}


def guardar(tabla: str, registros: list[dict]) -> int:
    """Guarda el lote en una sola transacción y devuelve cuántos registros envió."""
    if not registros:
        return 0
    # prepare_threshold=None: el pooler de Supabase no garantiza sentencias preparadas.
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], prepare_threshold=None) as conexion:
        with conexion.cursor() as cursor:
            cursor.executemany(_UPSERT[tabla], registros)
    return len(registros)
