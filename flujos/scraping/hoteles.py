"""Extracción de hoteles desde Google Hotels.

Google Hotels no acepta las fechas en la URL, así que se escriben en el
formulario como lo haría una persona. Igual que en vuelos, cada dato se toma de
las descripciones accesibles (aria-label) de la tarjeta:
  "Precios de Hotel cartagena DCa partir de $ 153.000"
  "4,1 de 5 estrellas de 654 reseñas, Hotel cartagena DC"
  "Servicios de Hotel cartagena DC, un Hotel de 3 estrellas.: Desayuno gratis, Wi-Fi gratis,"
"""

import re
import sys
from datetime import date
from urllib.parse import quote

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from scraping.navegador import SinResultados, abrir_pagina, verificar_bloqueo

FUENTE = "google_hotels"
SELECTOR_PRECIO = '[aria-label^="Precios de"][aria-label*="a partir de"]'

_PRECIO = re.compile(r"a partir de \$ ?([\d.]+)")
_PUNTUACION = re.compile(r"^([\d,]+) de 5 estrellas de")
_ESTRELLAS = re.compile(r"Hotel de (\d) estrellas")
_SERVICIOS = re.compile(r"^Servicios de .+?: (.+)$")

# Sube desde cada precio hasta la tarjeta completa: el contenedor más grande que
# todavía tiene un solo título (un nivel más arriba ya hay varios hoteles).
_JS_TARJETAS = """(selector) => {
  const tarjetas = new Map();
  for (const precio of document.querySelectorAll(selector)) {
    let nodo = precio;
    while (nodo && !nodo.querySelector('h2')) nodo = nodo.parentElement;
    while (nodo && nodo.parentElement && nodo.parentElement.querySelectorAll('h2').length === 1) nodo = nodo.parentElement;
    if (!nodo || tarjetas.has(nodo)) continue;
    tarjetas.set(nodo, {
      nombre: nodo.querySelector('h2').innerText.trim(),
      // Los servicios y la categoría solo vienen como texto, no como aria-label.
      etiquetas: [...nodo.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label'))
        .concat(nodo.innerText.split('\\n')),
    });
  }
  return [...tarjetas.values()];
}"""


def construir_url(ciudad: str) -> str:
    return f"https://www.google.com/travel/search?q={quote('hoteles en ' + ciudad)}&hl=es&gl=co&curr=COP"


def interpretar_tarjeta(nombre: str, etiquetas: list[str]) -> dict | None:
    """Convierte las descripciones de una tarjeta en un hotel; None si no trae precio."""
    hotel = {"nombre": nombre, "estrellas": None, "puntuacion": None, "servicios": []}
    for etiqueta in etiquetas:
        etiqueta = re.sub(r"\s+", " ", etiqueta).strip()
        if m := _PRECIO.search(etiqueta):
            hotel.setdefault("precio_noche_cop", int(m.group(1).replace(".", "")))
        if hotel["puntuacion"] is None and (m := _PUNTUACION.match(etiqueta)):
            hotel["puntuacion"] = float(m.group(1).replace(",", "."))
        if m := _ESTRELLAS.search(etiqueta):
            hotel["estrellas"] = int(m.group(1))
        if m := _SERVICIOS.match(etiqueta):
            hotel["servicios"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
    return hotel if nombre and "precio_noche_cop" in hotel else None


def _fijar_fechas(page: Page, entrada: date, salida: date) -> None:
    # El primer clic a veces llega antes de que la página esté lista y no abre el calendario.
    hecho = page.locator('button:has-text("Hecho"):visible')
    for _ in range(4):
        page.locator('input[aria-label="Entrada"]:visible').first.click()
        try:
            hecho.last.wait_for(state="visible", timeout=4_000)
            break
        except PlaywrightTimeout:
            page.keyboard.press("Escape")
            page.wait_for_timeout(1_500)
    else:
        raise SinResultados("No se abrió el calendario de Google Hotels")
    # Al abrir el calendario aparece un segundo par de campos; se escribe en ese.
    for campo, dia in (("Entrada", entrada), ("Salida", salida)):
        caja = page.locator(f'input[aria-label="{campo}"]:visible').last
        caja.fill(dia.strftime("%d/%m/%Y"), timeout=10_000)
        caja.press("Tab")
        page.wait_for_timeout(800)
    if hecho.count():  # a veces el calendario se cierra solo al completar la salida
        hecho.last.click(timeout=10_000)
    page.wait_for_timeout(5_000)  # la lista se recarga con los precios de esas fechas

    visible = page.locator('input[aria-label="Entrada"]:visible').first.input_value()
    if not re.search(rf"\b{entrada.day}\b", visible):
        raise SinResultados(f"Google no aplicó la fecha de entrada {entrada} (muestra '{visible}')")


def extraer_hoteles(ciudad: str, entrada: date, salida: date) -> list[dict]:
    """Abre la búsqueda y devuelve los hoteles listos para guardar en la tabla `hoteles`."""
    with abrir_pagina() as page:
        page.goto(construir_url(ciudad), wait_until="domcontentloaded", timeout=45_000)
        try:
            page.wait_for_selector(SELECTOR_PRECIO, state="attached", timeout=30_000)
        except PlaywrightTimeout:
            verificar_bloqueo(page)
            raise SinResultados(f"Sin hoteles visibles para {ciudad}") from None
        _fijar_fechas(page, entrada, salida)
        tarjetas = page.evaluate(_JS_TARJETAS, SELECTOR_PRECIO)

    hoteles = {}
    for tarjeta in tarjetas:
        hotel = interpretar_tarjeta(tarjeta["nombre"], tarjeta["etiquetas"])
        if hotel is not None:
            hoteles.setdefault(hotel["nombre"], hotel | {"ciudad": ciudad, "fuente": FUENTE})

    if not hoteles:
        raise SinResultados(f"Ningún hotel interpretable para {ciudad}")
    return list(hoteles.values())


if __name__ == "__main__":
    # Uso: python -m scraping.hoteles "Cartagena de Indias" 2026-11-06 2026-11-09
    ciudad, desde, hasta = sys.argv[1:4]
    encontrados = extraer_hoteles(ciudad, date.fromisoformat(desde), date.fromisoformat(hasta))
    print(f"{len(encontrados)} hoteles en {ciudad} del {desde} al {hasta}")
    for h in encontrados[:8]:
        print(h)
