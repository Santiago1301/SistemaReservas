"""Extracción de autos desde la fuente simulada (RentaYa).

La fuente entrega HTML estático, así que no hace falta navegador: se descarga
la página y se leen las tarjetas <article class="auto">.
"""

import os
import re
import sys
from html.parser import HTMLParser

import httpx

from scraping.navegador import SinResultados

FUENTE = "rentaya_simulada"
URL_FUENTE = os.environ.get("FUENTE_AUTOS_URL", "http://fuente-autos:8000")
CAMPOS = {"modelo", "proveedor", "categoria", "precio"}


class _LectorTarjetas(HTMLParser):
    """Junta el texto de cada campo dentro de cada <article class="auto">."""

    def __init__(self):
        super().__init__()
        self.tarjetas: list[dict] = []
        self._campo: str | None = None

    def handle_starttag(self, tag, attrs):
        clases = set((dict(attrs).get("class") or "").split())
        if tag == "article" and "auto" in clases:
            self.tarjetas.append({})
        elif self.tarjetas and (campo := clases & CAMPOS):
            self._campo = campo.pop()

    def handle_data(self, data):
        if self._campo:
            self.tarjetas[-1][self._campo] = data.strip()
            self._campo = None


def interpretar_html(html: str) -> list[dict]:
    lector = _LectorTarjetas()
    lector.feed(html)
    autos = []
    for tarjeta in lector.tarjetas:
        if not CAMPOS <= tarjeta.keys():
            continue
        autos.append({
            "proveedor": tarjeta["proveedor"],
            "modelo": tarjeta["modelo"],
            "categoria": tarjeta["categoria"],
            "precio_dia_cop": int(re.sub(r"\D", "", tarjeta["precio"])),  # "$ 185.000 / día"
        })
    return autos


def extraer_autos(ciudad: str) -> list[dict]:
    """Descarga la página de la ciudad y devuelve los autos listos para la tabla `autos`."""
    respuesta = httpx.get(f"{URL_FUENTE}/autos", params={"ciudad": ciudad}, timeout=15)
    respuesta.raise_for_status()  # un 503 de la fuente se convierte en error y Prefect reintenta
    autos = interpretar_html(respuesta.text)
    if not autos:
        raise SinResultados(f"Ningún auto interpretable para {ciudad}")
    return [auto | {"ciudad": ciudad, "fuente": FUENTE} for auto in autos]


if __name__ == "__main__":
    # Uso: python -m scraping.autos "Cartagena de Indias"
    encontrados = extraer_autos(sys.argv[1])
    print(f"{len(encontrados)} autos en {sys.argv[1]}")
    for a in encontrados[:8]:
        print(a)
