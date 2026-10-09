"""Registra los flujos en Prefect y se queda escuchando para ejecutarlos.

Cada flujo queda como un "deployment": se puede lanzar a mano desde el panel de
Prefect, por la API, o solo según su programación.
"""

import os
from datetime import timedelta

from prefect import serve

from ingesta import ingesta
from saga import saga_reserva

# INGESTA_PAUSADA=true registra la ingesta sin su programación automática
# (sigue pudiéndose lanzar a mano). Útil para no consultar a Google sin querer.
INGESTA_PAUSADA = os.environ.get("INGESTA_PAUSADA", "false").lower() == "true"

if __name__ == "__main__":
    serve(
        ingesta.to_deployment(
            name="programada",
            interval=timedelta(hours=2),
            paused=INGESTA_PAUSADA,
            description="Scraping de vuelos, hoteles y autos, y carga en Supabase.",
        ),
        saga_reserva.to_deployment(
            name="orquestada",
            description="SAGA de reserva de un paquete. La lanza el servicio de órdenes.",
        ),
    )
