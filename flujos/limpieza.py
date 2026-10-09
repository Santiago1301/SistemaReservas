"""Limpieza y validación de los registros extraídos, antes de guardarlos.

Descarta lo que la base rechazaría (precios no positivos, campos vacíos) y
normaliza el texto, para que un registro raro no tumbe el lote completo.
"""

import re


def _texto(valor: str) -> str:
    # Google usa espacios y guiones "de no separación"; se llevan a los normales.
    return re.sub(r"\s+", " ", valor.replace("‑", "-")).strip()


def vuelos(registros: list[dict]) -> list[dict]:
    limpios = []
    for r in registros:
        aerolinea = _texto(r["aerolinea"])
        if not aerolinea or r["precio_cop"] <= 0:
            continue
        limpios.append(r | {"aerolinea": aerolinea})
    return limpios


def hoteles(registros: list[dict]) -> list[dict]:
    limpios = []
    for r in registros:
        nombre = _texto(r["nombre"])
        if not nombre or r["precio_noche_cop"] <= 0:
            continue
        estrellas, puntuacion = r["estrellas"], r["puntuacion"]
        limpios.append(r | {
            "nombre": nombre,
            "estrellas": estrellas if estrellas and 1 <= estrellas <= 5 else None,
            "puntuacion": puntuacion if puntuacion is not None and 0 <= puntuacion <= 5 else None,
            "servicios": list(dict.fromkeys(_texto(s) for s in r["servicios"] if _texto(s))),
        })
    return limpios


def autos(registros: list[dict]) -> list[dict]:
    limpios = []
    for r in registros:
        modelo, proveedor = _texto(r["modelo"]), _texto(r["proveedor"])
        if not modelo or not proveedor or r["precio_dia_cop"] <= 0:
            continue
        limpios.append(r | {"modelo": modelo, "proveedor": proveedor, "categoria": _texto(r["categoria"])})
    return limpios
