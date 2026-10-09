"""Apertura del navegador compartida por los scrapers."""

from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright

SENALES_BLOQUEO = ["unusual traffic", "tráfico inusual", "are you a robot", "no soy un robot"]


class BloqueoDetectado(Exception):
    """El sitio respondió con una verificación anti-bot en vez de resultados."""


class SinResultados(Exception):
    """La página cargó pero no mostró ningún resultado."""


@contextmanager
def abrir_pagina():
    """Entrega una página de Chromium sin ventana y la cierra al terminar."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        try:
            contexto = navegador.new_context(
                locale="es-CO", timezone_id="America/Bogota", viewport={"width": 1366, "height": 900}
            )
            yield contexto.new_page()
        finally:
            navegador.close()


def verificar_bloqueo(page: Page) -> None:
    texto = page.inner_text("body").lower()
    # Respuesta de Google cuando recibe demasiadas consultas seguidas desde una red.
    if "se ha producido un error" in texto:
        raise BloqueoDetectado("Google devolvió un error temporal (posible límite de consultas)")
    if "/sorry/" in page.url or any(senal in texto for senal in SENALES_BLOQUEO):
        raise BloqueoDetectado(f"Verificación anti-bot en {page.url[:80]}")
