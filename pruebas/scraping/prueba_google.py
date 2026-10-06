"""Prueba exploratoria contra Google Flights (y, de paso, Google Hotels).

Mismos parámetros que las pruebas anteriores. No intenta resolver ni esquivar CAPTCHAs.
"""

import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PAUSA_ENTRE_BUSQUEDAS = 8  # segundos
SENALES_BLOQUEO = ["captcha", "are you a robot", "eres un robot", "verify you are human",
                   "access denied", "acceso denegado", "unusual traffic"]

# SALIDAS_DIR permite guardar aparte la corrida hecha dentro de Docker.
SALIDAS = Path(__file__).parent / os.environ.get("SALIDAS_DIR", "salidas")

BUSQUEDAS = {
    "google_vuelos": (
        "https://www.google.com/travel/flights"
        "?q=Flights%20from%20BOG%20to%20CTG%20on%202026-11-06%20through%202026-11-09"
        "&curr=COP&hl=es&gl=co"
    ),
    "google_hoteles": (
        "https://www.google.com/travel/search"
        "?q=hoteles%20en%20Cartagena%20de%20Indias&hl=es&gl=co&curr=COP"
    ),
}

# Google muestra "473.590 COP" en vuelos y "$ 223.026" en hoteles.
PRECIO = re.compile(r"\d{1,3}(?:\.\d{3})+\s?COP|\$\s?\d{1,3}(?:\.\d{3})+")


def main():
    SALIDAS.mkdir(exist_ok=True)
    resultados = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(
            locale="es-CO", timezone_id="America/Bogota", viewport={"width": 1366, "height": 900}
        )
        page = contexto.new_page()
        for i, (nombre, url) in enumerate(BUSQUEDAS.items()):
            if i:
                time.sleep(PAUSA_ENTRE_BUSQUEDAS)
            print(f"→ {nombre}...", flush=True)
            inicio = time.time()
            respuesta = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(12_000)
            texto = page.inner_text("body")
            html = page.content()
            precios = PRECIO.findall(texto)
            elementos = page.query_selector_all("li")
            con_precio = [e.inner_text().strip().replace("\n", " | ") for e in elementos]
            con_precio = [t for t in con_precio if PRECIO.search(t) and len(t) < 400]
            resultados.append({
                "busqueda": nombre,
                "status_http": respuesta.status if respuesta else None,
                "segundos": round(time.time() - inicio, 1),
                "url_final": page.url[:150],
                "titulo": page.title(),
                # En el texto visible: el HTML de Google siempre carga scripts de reCAPTCHA.
                "senales_bloqueo": [s for s in SENALES_BLOQUEO if s in texto.lower()],
                "precios_visibles": len(precios),
                "elementos_de_lista_con_precio": len(con_precio),
                "muestra": con_precio[:5],
            })
            (SALIDAS / f"{nombre}.html").write_text(html, encoding="utf-8")
            page.screenshot(path=SALIDAS / f"{nombre}.png")
        navegador.close()

    (SALIDAS / "resumen_google.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultados, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
