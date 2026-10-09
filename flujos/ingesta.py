"""Flow de ingesta: scraping distribuido en Dask, orquestado y observado por Prefect.

Por cada destino lanza tres cadenas independientes (vuelos, hoteles, autos).
Cada cadena tiene dos tareas: extraer+limpiar y guardar. Todas corren en los
workers de Dask; Prefect registra estados y reintentos.
"""

import os
import random
import time
from datetime import date

from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner

import limpieza
import persistencia
from scraping.autos import extraer_autos
from scraping.hoteles import extraer_hoteles
from scraping.vuelos import extraer_vuelos

ORIGEN = "BOG"
DESTINOS = {"CTG": "Cartagena de Indias", "MDE": "Medellín", "CLO": "Cali", "SMR": "Santa Marta"}

# Política de reintentos ante fallos de red o de extracción. Las esperas crecen
# para dar tiempo a que un límite temporal de la fuente se levante, y varían al
# azar para que varias tareas no reintenten todas en el mismo instante.
REINTENTOS = {"retries": 3, "retry_delay_seconds": [15, 45, 120], "retry_jitter_factor": 0.3}


def _pausa_de_cortesia() -> None:
    """Espacia las consultas a Google para no parecer una ráfaga automatizada."""
    time.sleep(random.uniform(1, 4))


@task(name="extraer-vuelos", task_run_name="extraer-vuelos-{origen}-{destino}", **REINTENTOS)
def tarea_vuelos(origen: str, destino: str, fecha: date) -> list[dict]:
    _pausa_de_cortesia()
    registros = limpieza.vuelos(extraer_vuelos(origen, destino, fecha))
    get_run_logger().info("%s-%s: %d vuelos extraídos", origen, destino, len(registros))
    return registros


@task(name="extraer-hoteles", task_run_name="extraer-hoteles-{ciudad}", **REINTENTOS)
def tarea_hoteles(ciudad: str, entrada: date, salida: date) -> list[dict]:
    _pausa_de_cortesia()
    registros = limpieza.hoteles(extraer_hoteles(ciudad, entrada, salida))
    get_run_logger().info("%s: %d hoteles extraídos", ciudad, len(registros))
    return registros


@task(name="extraer-autos", task_run_name="extraer-autos-{ciudad}", **REINTENTOS)
def tarea_autos(ciudad: str) -> list[dict]:
    registros = limpieza.autos(extraer_autos(ciudad))
    get_run_logger().info("%s: %d autos extraídos", ciudad, len(registros))
    return registros


@task(name="guardar", task_run_name="guardar-{tabla}-{etiqueta}", retries=2, retry_delay_seconds=5)
def tarea_guardar(tabla: str, etiqueta: str, registros: list[dict]) -> int:
    guardados = persistencia.guardar(tabla, registros)
    get_run_logger().info("%s (%s): %d registros guardados en Supabase", tabla, etiqueta, guardados)
    return guardados


@flow(
    name="ingesta",
    task_runner=DaskTaskRunner(address=os.environ.get("DASK_SCHEDULER", "tcp://dask-scheduler:8786")),
)
def ingesta(fecha_ida: date = date(2026, 11, 6), fecha_regreso: date = date(2026, 11, 9)) -> dict:
    log = get_run_logger()

    # submit() entrega la tarea a Dask y devuelve de inmediato; pasar el resultado
    # pendiente de "extraer" a "guardar" es lo que encadena las dos tareas.
    cadenas = []
    for iata, ciudad in DESTINOS.items():
        vuelos = tarea_vuelos.submit(ORIGEN, iata, fecha_ida)
        hoteles = tarea_hoteles.submit(ciudad, fecha_ida, fecha_regreso)
        autos = tarea_autos.submit(ciudad)
        cadenas += [
            ("vuelos", iata, tarea_guardar.submit("vuelos", iata, vuelos)),
            ("hoteles", ciudad, tarea_guardar.submit("hoteles", ciudad, hoteles)),
            ("autos", ciudad, tarea_guardar.submit("autos", ciudad, autos)),
        ]

    resumen = {"vuelos": 0, "hoteles": 0, "autos": 0}
    fallidas = []
    for tabla, etiqueta, futuro in cadenas:
        try:
            resumen[tabla] += futuro.result()
        except Exception as error:  # una cadena fallida no debe impedir contar las demás
            fallidas.append(f"{tabla}-{etiqueta}")
            log.warning("Cadena %s-%s falló tras los reintentos: %s", tabla, etiqueta, error)

    log.info("Ingesta terminada: %s | cadenas fallidas: %s", resumen, fallidas or "ninguna")
    if fallidas:
        # Lo ya guardado se conserva; el flow queda en rojo para que el fallo sea visible.
        raise RuntimeError(f"{len(fallidas)} de {len(cadenas)} cadenas fallaron: {', '.join(fallidas)}")
    return resumen


if __name__ == "__main__":
    ingesta()
