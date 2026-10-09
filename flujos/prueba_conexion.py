"""Prueba de humo: un flow de Prefect reparte tareas entre los workers de Dask.

No hace scraping. Solo confirma que Prefect, el scheduler y los workers se ven
entre sí y que las tareas quedan registradas en el panel de Prefect.
"""

import socket

from prefect import flow, task
from prefect_dask import DaskTaskRunner


@task(retries=2, retry_delay_seconds=2)
def cuadrado(n: int) -> dict:
    return {"n": n, "resultado": n * n, "worker": socket.gethostname()}


@flow(name="prueba-conexion", task_runner=DaskTaskRunner(address="tcp://dask-scheduler:8786"))
def prueba_conexion() -> list[dict]:
    resultados = [futuro.result() for futuro in cuadrado.map(range(8))]
    workers = sorted({r["worker"] for r in resultados})
    print(f"{len(resultados)} tareas ejecutadas en {len(workers)} worker(s): {workers}")
    return resultados


if __name__ == "__main__":
    prueba_conexion()
