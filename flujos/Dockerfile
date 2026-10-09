# Imagen única para todo lo que corre en Python alrededor de los flujos:
# servidor de Prefect, scheduler de Dask y workers de Dask. Compartirla garantiza
# que todos tengan exactamente las mismas versiones, requisito de Dask.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app
# Los comandos `dask scheduler` y `dask worker` no buscan módulos en la carpeta
# actual; sin esto no encuentran el código de los flujos al recibir una tarea.
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
