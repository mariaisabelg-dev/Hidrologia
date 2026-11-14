"""Utilidades geográficas: lectura de coordenadas y distancia geodésica."""

from __future__ import annotations

import math
import re

RADIO_TIERRA_KM = 6371.0088  # radio medio (IUGG)

# Recuadro aproximado de Colombia (continental + San Andrés y Providencia).
LAT_MIN, LAT_MAX = -4.30, 13.50
LON_MIN, LON_MAX = -82.00, -66.80


class CoordenadaInvalida(ValueError):
    pass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia ortodrómica (Haversine) en km entre dos puntos en grados decimales."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(a))


def _gms_a_decimal(numeros: list[float]) -> float:
    g, m, s = (numeros + [0.0, 0.0])[:3]
    if not (0 <= m < 60 and 0 <= s < 60):
        raise CoordenadaInvalida("Minutos y segundos deben estar entre 0 y 60.")
    signo = -1 if g < 0 else 1
    return signo * (abs(g) + m / 60 + s / 3600)


def leer_coordenadas(texto: str) -> tuple[float, float]:
    """Convierte un texto en (latitud, longitud) en grados decimales.

    Formatos aceptados (separador decimal: punto):
      "6.2442, -75.5812"
      "6.2442 -75.5812"
      "6°14'39.1\"N 75°34'52.3\"W"   (también O para Oeste)
      "6 14 39.1 N, 75 34 52.3 W"
      "6°14.65'N 75°34.87'W"        (grados y minutos decimales)
    El orden siempre es latitud y luego longitud.
    """
    t = texto.upper().replace("’", "'").replace("”", '"').replace("″", '"').replace("′", "'")
    tokens = re.findall(r"-?\d+(?:\.\d+)?|[NSEWO]", t)
    numeros = [float(x) for x in tokens if x not in "NSEWO"]
    letras = [x for x in tokens if x in "NSEWO"]

    if len(numeros) == 2:
        lat, lon = numeros
    elif len(numeros) in (4, 6):
        mitad = len(numeros) // 2
        lat, lon = _gms_a_decimal(numeros[:mitad]), _gms_a_decimal(numeros[mitad:])
    else:
        raise CoordenadaInvalida(
            f"No pude interpretar '{texto}'. Use p. ej. '6.2442, -75.5812' o "
            "'6°14'39\"N 75°34'52\"W' (latitud primero, punto como separador decimal)."
        )

    if letras:
        if len(letras) != 2 or letras[0] not in "NS" or letras[1] not in "EWO":
            raise CoordenadaInvalida("Los hemisferios deben ir como N/S para latitud y E/W/O para longitud.")
        lat = -abs(lat) if letras[0] == "S" else abs(lat)
        lon = -abs(lon) if letras[1] in "WO" else abs(lon)

    validar_en_colombia(lat, lon)
    return lat, lon


def leer_valor(texto: str, eje: str) -> float:
    """Lee UNA coordenada ('lat' o 'lon') en decimal o GMS. Ej: '6.2442', '6°14'39\"N', '-75.5812', '75 34 52 W'."""
    t = texto.upper().replace("’", "'").replace("”", '"').replace("″", '"').replace("′", "'")
    tokens = re.findall(r"-?\d+(?:\.\d+)?|[NSEWO]", t)
    numeros = [float(x) for x in tokens if x not in "NSEWO"]
    letras = [x for x in tokens if x in "NSEWO"]
    if not 1 <= len(numeros) <= 3 or len(letras) > 1:
        raise CoordenadaInvalida(f"No pude interpretar '{texto}'. Ej: 6.2442 o 6°14'39\"N.")
    valor = numeros[0] if len(numeros) == 1 else _gms_a_decimal(numeros)
    if letras:
        validas = "NS" if eje == "lat" else "EWO"
        if letras[0] not in validas:
            raise CoordenadaInvalida(f"Para la {'latitud' if eje == 'lat' else 'longitud'} use {'/'.join(validas)}.")
        valor = -abs(valor) if letras[0] in "SWO" else abs(valor)
    return valor


def validar_en_colombia(lat: float, lon: float) -> None:
    if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
        return
    pista = ""
    if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= -lon <= LON_MAX:
        pista = " La longitud en Colombia es Oeste (negativa); ¿le faltó el signo '-' o la 'W'?"
    elif LAT_MIN <= lon <= LAT_MAX and LON_MIN <= lat <= LON_MAX:
        pista = " Parece que latitud y longitud están invertidas (va primero la latitud)."
    raise CoordenadaInvalida(
        f"El punto ({lat:.5f}, {lon:.5f}) está fuera de Colombia "
        f"(lat {LAT_MIN} a {LAT_MAX}, lon {LON_MIN} a {LON_MAX}).{pista}"
    )
