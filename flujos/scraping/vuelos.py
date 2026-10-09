"""Extracción de vuelos de solo ida desde Google Flights.

Cada resultado trae una descripción accesible (aria-label) con todos los datos
en una frase, por ejemplo:
  "A partir de 192440 pesos colombianos. Vuelo directo de JetSMART. ... Sale de
   Aeropuerto Internacional El Dorado el viernes, noviembre 6 a las 4:10. Llega
   a ... a las 5:47. Duración total: 1 h 37 min."
Se interpreta esa frase en vez de las clases CSS, que Google cambia seguido.
"""

import re
import sys
from datetime import date
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from scraping.navegador import SinResultados, abrir_pagina, verificar_bloqueo

FUENTE = "google_flights"
SELECTOR_VUELO = 'li [aria-label*="pesos colombianos"][aria-label*="Duración total"]'

_PRECIO = re.compile(r"(\d+) pesos colombianos")
_ESCALAS = re.compile(r"Vuelo con (\d+) escalas?")
_AEROLINEA = re.compile(r"Vuelo (?:directo|con \d+ escalas?) de (.+?)\.(?: |$)")
_SALIDA = re.compile(r"Sale de .+? a las (\d{1,2}:\d{2})")
_LLEGADA = re.compile(r"Llega a .+? a las (\d{1,2}:\d{2})")
_DURACION = re.compile(r"Duración total: (?:(\d+) h)? ?(?:(\d+) min)?")


def construir_url(origen: str, destino: str, fecha: date) -> str:
    consulta = f"Flights from {origen} to {destino} on {fecha.isoformat()} one way"
    return f"https://www.google.com/travel/flights?q={quote(consulta)}&curr=COP&hl=es&gl=co"


def interpretar_etiqueta(etiqueta: str) -> dict | None:
    """Convierte la descripción de un resultado en un vuelo; None si no se entiende."""
    etiqueta = re.sub(r"\s+", " ", etiqueta)  # Google usa espacios de no separación
    precio, aerolinea = _PRECIO.search(etiqueta), _AEROLINEA.search(etiqueta)
    salida, llegada = _SALIDA.search(etiqueta), _LLEGADA.search(etiqueta)
    duracion = _DURACION.search(etiqueta)
    if not (precio and aerolinea and salida and llegada):
        return None

    escalas = _ESCALAS.search(etiqueta)
    horas, minutos = (int(g or 0) for g in duracion.groups()) if duracion else (0, 0)
    return {
        "aerolinea": aerolinea.group(1).strip(),
        "hora_salida": salida.group(1).zfill(5),
        "hora_llegada": llegada.group(1).zfill(5),
        "duracion_min": horas * 60 + minutos or None,
        "escalas": int(escalas.group(1)) if escalas else 0,
        "precio_cop": int(precio.group(1)),
    }


def extraer_vuelos(origen: str, destino: str, fecha: date) -> list[dict]:
    """Abre la búsqueda y devuelve los vuelos listos para guardar en la tabla `vuelos`."""
    with abrir_pagina() as page:
        page.goto(construir_url(origen, destino, fecha), wait_until="domcontentloaded", timeout=45_000)
        try:
            page.wait_for_selector(SELECTOR_VUELO, timeout=30_000)
        except PlaywrightTimeout:
            verificar_bloqueo(page)
            raise SinResultados(f"Sin vuelos visibles para {origen}-{destino} el {fecha}") from None
        page.wait_for_timeout(2_000)  # el resto de la lista termina de dibujarse
        etiquetas = page.eval_on_selector_all(SELECTOR_VUELO, "els => els.map(e => e.getAttribute('aria-label'))")

    vuelos = {}
    for etiqueta in etiquetas:
        vuelo = interpretar_etiqueta(etiqueta)
        if vuelo is None:
            continue
        vuelo |= {"origen": origen, "destino": destino, "fecha_salida": fecha.isoformat(), "fuente": FUENTE}
        # Misma clave única que la tabla; si Google repite un vuelo, queda el más barato.
        clave = (vuelo["aerolinea"], vuelo["hora_salida"])
        if clave not in vuelos or vuelo["precio_cop"] < vuelos[clave]["precio_cop"]:
            vuelos[clave] = vuelo

    if not vuelos:
        raise SinResultados(f"Ningún resultado interpretable para {origen}-{destino} el {fecha}")
    return list(vuelos.values())


if __name__ == "__main__":
    # Uso: python -m scraping.vuelos BOG CTG 2026-11-06
    origen, destino, dia = sys.argv[1:4]
    encontrados = extraer_vuelos(origen, destino, date.fromisoformat(dia))
    print(f"{len(encontrados)} vuelos {origen}-{destino} el {dia}")
    for v in encontrados[:8]:
        print(v)
