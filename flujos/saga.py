"""SAGA orquestada de la reserva de un paquete.

El flow es el orquestador: llama a cada microservicio en orden (vuelo, hotel,
auto, pago). Si un paso falla, ejecuta las compensaciones de lo ya hecho en
orden inverso y deja la orden CANCELADA. Si todos pasan, la deja CONFIRMADA.
"""

import os

import httpx
from prefect import flow, get_run_logger, task
from prefect.states import Completed

URL = {
    "VUELO": os.environ.get("VUELOS_URL", "http://vuelos:8000"),
    "HOTEL": os.environ.get("HOTELES_URL", "http://hoteles:8000"),
    "AUTO": os.environ.get("AUTOS_URL", "http://autos:8000"),
    "ORDENES": os.environ.get("ORDENES_URL", "http://ordenes:8000"),
}


class ErrorDeNegocio(Exception):
    """El servicio rechazó la operación (sin cupos, no existe...). Reintentar no lo arregla."""


class ErrorTecnico(Exception):
    """El servicio falló por dentro (error 5xx). Puede ser pasajero: se reintenta."""


def _reintentar_si_es_tecnico(task, task_run, state) -> bool:
    try:
        state.result()
    except ErrorDeNegocio:
        return False
    except Exception:
        return True
    return True


# Acciones: 2 reintentos solo ante fallos técnicos (red, error 5xx del servicio).
ACCION = {"retries": 2, "retry_delay_seconds": 3, "retry_condition_fn": _reintentar_si_es_tecnico}
# Compensaciones: deben terminar bien, así que insisten más.
COMPENSACION = {"retries": 5, "retry_delay_seconds": 3}


def _llamar(url: str, cuerpo: dict | None = None) -> dict:
    respuesta = httpx.post(url, json=cuerpo, timeout=30)
    if respuesta.is_error:
        try:
            detalle = respuesta.json().get("detail", respuesta.text)
        except ValueError:
            detalle = respuesta.text
        mensaje = f"{detalle} (HTTP {respuesta.status_code})"
        raise ErrorDeNegocio(mensaje) if respuesta.status_code < 500 else ErrorTecnico(mensaje)
    return respuesta.json()


def _falla(orden: dict, paso: str) -> bool:
    return orden["simular_fallo_en"] == paso


# ----- Acciones -----

@task(name="reservar-vuelo", **ACCION)
def reservar_vuelo(orden: dict) -> dict:
    return _llamar(f"{URL['VUELO']}/reservas", {
        "orden_id": orden["id"], "vuelo_id": orden["vuelo_id"], "pasajeros": orden["pasajeros"],
        "simular_fallo": _falla(orden, "VUELO"),
    })


@task(name="reservar-hotel", **ACCION)
def reservar_hotel(orden: dict) -> dict:
    return _llamar(f"{URL['HOTEL']}/reservas", {
        "orden_id": orden["id"], "hotel_id": orden["hotel_id"],
        "fecha_entrada": orden["fecha_inicio"], "fecha_salida": orden["fecha_fin"],
        "simular_fallo": _falla(orden, "HOTEL"),
    })


@task(name="reservar-auto", **ACCION)
def reservar_auto(orden: dict) -> dict:
    return _llamar(f"{URL['AUTO']}/reservas", {
        "orden_id": orden["id"], "auto_id": orden["auto_id"],
        "fecha_recogida": orden["fecha_inicio"], "fecha_devolucion": orden["fecha_fin"],
        "simular_fallo": _falla(orden, "AUTO"),
    })


@task(name="cobrar", **ACCION)
def cobrar(orden: dict) -> dict:
    return _llamar(f"{URL['ORDENES']}/ordenes/{orden['id']}/pago", {"simular_fallo": _falla(orden, "PAGO")})


# ----- Compensaciones -----

@task(name="cancelar-vuelo", **COMPENSACION)
def cancelar_vuelo(orden: dict) -> dict:
    return _llamar(f"{URL['VUELO']}/reservas/{orden['id']}/cancelar")


@task(name="cancelar-hotel", **COMPENSACION)
def cancelar_hotel(orden: dict) -> dict:
    return _llamar(f"{URL['HOTEL']}/reservas/{orden['id']}/cancelar")


@task(name="cancelar-auto", **COMPENSACION)
def cancelar_auto(orden: dict) -> dict:
    return _llamar(f"{URL['AUTO']}/reservas/{orden['id']}/cancelar")


@task(name="reembolsar", **COMPENSACION)
def reembolsar(orden: dict) -> dict:
    return _llamar(f"{URL['ORDENES']}/ordenes/{orden['id']}/pago/reembolsar")


PASOS = [
    ("VUELO", reservar_vuelo, cancelar_vuelo),
    ("HOTEL", reservar_hotel, cancelar_hotel),
    ("AUTO", reservar_auto, cancelar_auto),
    ("PAGO", cobrar, reembolsar),
]


def _bitacora(orden_id: str, paso: str, tipo: str, estado: str, detalle: str | None = None) -> None:
    _llamar(f"{URL['ORDENES']}/ordenes/{orden_id}/pasos",
            {"paso": paso, "tipo": tipo, "estado": estado, "detalle": detalle})


def _estado(orden_id: str, estado: str, motivo: str | None = None) -> None:
    _llamar(f"{URL['ORDENES']}/ordenes/{orden_id}/estado", {"estado": estado, "motivo_fallo": motivo})


@flow(name="saga-reserva", flow_run_name="saga-{orden_id}")
def saga_reserva(orden_id: str):
    log = get_run_logger()
    respuesta = httpx.get(f"{URL['ORDENES']}/ordenes/{orden_id}", timeout=30)
    respuesta.raise_for_status()
    orden = respuesta.json()

    por_compensar = []
    for paso, accion, compensacion in PASOS:
        # El paso entra a la lista antes de ejecutarse: si falla a medias (por ejemplo,
        # reservó pero la respuesta se perdió), su compensación también debe correr.
        por_compensar.append((paso, compensacion))
        try:
            accion(orden)
            _bitacora(orden_id, paso, "ACCION", "OK")
        except Exception as error:
            motivo = f"Falló {paso}: {error}"
            log.warning("%s. Se compensan %d paso(s).", motivo, len(por_compensar))
            _bitacora(orden_id, paso, "ACCION", "FALLO", str(error))
            _estado(orden_id, "COMPENSANDO", motivo)

            for paso_hecho, compensar in reversed(por_compensar):
                resultado = compensar(orden)
                _bitacora(orden_id, paso_hecho, "COMPENSACION", "OK", f"Resultado: {resultado['estado']}")

            _estado(orden_id, "CANCELADA")
            return Completed(name="Compensada", message=motivo)

    _estado(orden_id, "CONFIRMADA")
    log.info("Orden %s confirmada", orden_id)
    return Completed(name="Confirmada", message="Paquete reservado y cobrado")
