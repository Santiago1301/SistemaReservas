"""Sitio simulado de alquiler de autos: la fuente que scrapea la ingesta.

Imita lo incómodo de una fuente real: responde HTML (no JSON), tarda un tiempo
variable, falla a veces y cambia sus precios cada hora.
"""

import asyncio
import os
import random
from datetime import datetime, timezone
from html import escape

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

TASA_FALLO = float(os.environ.get("TASA_FALLO", "0.3"))
LATENCIA_MAX_S = float(os.environ.get("LATENCIA_MAX_S", "2"))

# ciudad -> factor de precio (las ciudades turísticas son más caras)
CIUDADES = {"Bogotá": 1.0, "Medellín": 1.05, "Cali": 0.95, "Cartagena de Indias": 1.25, "Santa Marta": 1.15}
# proveedor -> factor de precio
PROVEEDORES = {"RentaCaribe": 1.0, "AndesCar": 1.08, "MoviRent": 0.93, "RutaLibre": 1.15}
# (modelo, categoría, precio base por día en COP)
FLOTA = [
    ("Chevrolet Spark", "Económico", 95_000),
    ("Kia Picanto", "Económico", 105_000),
    ("Renault Logan", "Sedán", 140_000),
    ("Mazda 2", "Sedán", 165_000),
    ("Renault Duster", "SUV", 210_000),
    ("Toyota Corolla Cross", "SUV", 280_000),
    ("Toyota Hilux", "Camioneta", 340_000),
]

app = FastAPI(title="RentaYa (fuente simulada de autos)")


def ofertas(ciudad: str) -> list[dict]:
    hora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H")
    resultado = []
    for proveedor, factor_proveedor in PROVEEDORES.items():
        # Cada proveedor tiene una parte fija de la flota en cada ciudad.
        flota = random.Random(f"{ciudad}|{proveedor}").sample(FLOTA, k=4)
        for modelo, categoria, base in flota:
            variacion = random.Random(f"{ciudad}|{proveedor}|{modelo}|{hora}").uniform(0.92, 1.08)
            precio = round(base * CIUDADES[ciudad] * factor_proveedor * variacion, -3)
            resultado.append(
                {"proveedor": proveedor, "modelo": modelo, "categoria": categoria, "precio": int(precio)}
            )
    return sorted(resultado, key=lambda o: o["precio"])


def pagina(titulo: str, cuerpo: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{escape(titulo)} · RentaYa</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1f2933; }}
    .auto {{ display: flex; justify-content: space-between; align-items: center;
             border: 1px solid #d9e2ec; border-radius: 8px; padding: .8rem 1rem; margin: .6rem 0; }}
    .modelo {{ font-weight: 600; margin: 0; font-size: 1.05rem; }}
    .proveedor, .categoria {{ color: #52606d; font-size: .9rem; margin-right: .8rem; }}
    .precio {{ font-weight: 700; color: #0b6e4f; white-space: nowrap; }}
  </style>
</head>
<body>
  <h1>RentaYa</h1>
  {cuerpo}
</body>
</html>"""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def inicio() -> str:
    enlaces = "".join(f'<li><a href="/autos?ciudad={escape(c)}">{escape(c)}</a></li>' for c in CIUDADES)
    return pagina("Alquiler de autos", f"<p>Elige una ciudad:</p><ul>{enlaces}</ul>")


@app.get("/autos", response_class=HTMLResponse)
async def autos(ciudad: str = Query(...)) -> str:
    if ciudad not in CIUDADES:
        raise HTTPException(status_code=404, detail=f"No operamos en {ciudad}")

    await asyncio.sleep(random.uniform(0.2, LATENCIA_MAX_S))
    if random.random() < TASA_FALLO:
        raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")

    tarjetas = "".join(
        f"""
  <article class="auto">
    <div>
      <h2 class="modelo">{escape(o["modelo"])}</h2>
      <span class="proveedor">{escape(o["proveedor"])}</span>
      <span class="categoria">{escape(o["categoria"])}</span>
    </div>
    <span class="precio">$ {o["precio"]:,} / día</span>
  </article>""".replace(",", ".")
        for o in ofertas(ciudad)
    )
    return pagina(f"Autos en {ciudad}", f'<p>Autos disponibles en <strong>{escape(ciudad)}</strong></p>{tarjetas}')
