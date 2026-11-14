"""Estaciones cercanas cuyos datos NO se pueden descargar automáticamente.

Sirve para el flujo semiautomático: el programa dice qué estaciones conviene
conseguir a mano (DHIME, solicitud a la entidad…) y de dónde. Fuentes:
  - Catálogo Nacional de Estaciones (datos.gov.co hp9r-jxuu): todas las estaciones
    activas que miden precipitación, de cualquier tecnología y entidad (incluye las
    convencionales del IDEAM, CAR, EPM, Cenicafé…).
  - SIATA (siata.gov.co/data/siata_app/Pluviometrica.json): pluviómetros del Valle de
    Aburrá; publica solo valores actuales, la historia se pide a SIATA.
"""

from __future__ import annotations

import logging

import pandas as pd

from .geo import haversine_km
from .ideam import CATEGORIAS_CON_PRECIPITACION, DS_CATALOGO, normalizar_codigo, sigla_entidad
from .red import ClienteJSON
from .socrata import ClienteSocrata

log = logging.getLogger(__name__)

URL_SIATA = "https://siata.gov.co/data/siata_app/Pluviometrica.json"
DHIME = "DHIME: descargar en atencionciudadano.ideam.gov.co"


def _donde(entidad: str) -> str:
    if entidad == "IDEAM":
        return DHIME
    return f"Solicitar a {entidad} (también puede estar en DHIME si el IDEAM la recibe)"


def _catalogo_nacional(cliente: ClienteSocrata) -> list[dict]:
    categorias = ", ".join(f"'{c}'" for c in CATEGORIAS_CON_PRECIPITACION)
    filas = cliente.consultar(
        DS_CATALOGO,
        {
            "$select": "codigo, nombre, categoria, tecnologia, entidad, departamento, municipio, "
            "latitud, longitud, altitud, fecha_instalacion",
            "$where": f"estado = 'Activa' AND categoria in ({categorias})",
            "$limit": 50000,
        },
    )
    vistos, out = set(), []
    for f in filas:
        try:
            lat, lon = float(f["latitud"]), float(f["longitud"])
        except (KeyError, TypeError, ValueError):
            continue
        codigo = normalizar_codigo(f.get("codigo"))
        if codigo in vistos:
            continue
        vistos.add(codigo)
        entidad = sigla_entidad(f.get("entidad", ""))
        out.append(
            {
                "Código": codigo,
                "Nombre": f.get("nombre", ""),
                "Entidad": entidad,
                "Categoría": f.get("categoria", ""),
                "Tecnología": f.get("tecnologia", ""),
                "Departamento": f.get("departamento", ""),
                "Municipio": f.get("municipio", ""),
                "Latitud": lat,
                "Longitud": lon,
                "Elevación (msnm)": pd.to_numeric(f.get("altitud"), errors="coerce"),
                "Instalada": f.get("fecha_instalacion", ""),
                "Dónde obtener los datos": _donde(entidad),
            }
        )
    return out


def _siata() -> list[dict]:
    datos = ClienteJSON(timeout_s=60).get(URL_SIATA)
    filas = datos.get("estaciones", datos) if isinstance(datos, dict) else datos
    out = []
    for e in filas:
        try:
            lat, lon = float(e["latitud"]), float(e["longitud"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(
            {
                "Código": f"SIATA-{e.get('codigo')}",
                "Nombre": e.get("nombre", ""),
                "Entidad": "SIATA",
                "Categoría": "Pluviométrica",
                "Tecnología": "Automática con telemetría",
                "Departamento": "Antioquia",
                "Municipio": e.get("ciudad", ""),
                "Latitud": lat,
                "Longitud": lon,
                "Elevación (msnm)": None,
                "Instalada": "",
                "Dónde obtener los datos": "Solicitar histórico a SIATA (en línea solo publica valores actuales)",
            }
        )
    return out


def estaciones_para_descarga_manual(
    lat: float, lon: float, excluir: set[str], n_ideam: int = 10, n_otras: int = 10, radio_km: float = 50
) -> pd.DataFrame:
    """Estaciones cercanas (≤ `radio_km`) sin descarga automática, que no están en `excluir`.

    Se listan por separado las `n_ideam` más cercanas del IDEAM (descargables en DHIME,
    incluidas las convencionales de series largas) y las `n_otras` más cercanas de otras
    entidades (requieren solicitud), para que unas no tapen a las otras.
    """
    filas: list[dict] = []
    for nombre, funcion in [("catálogo nacional", lambda: _catalogo_nacional(ClienteSocrata())), ("SIATA", _siata)]:
        try:
            filas += funcion()
        except Exception as e:  # noqa: BLE001 - es un reporte complementario
            log.warning("No se pudo consultar %s para la lista de descarga manual: %s", nombre, e)
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    df = df[~df["Código"].isin(excluir)]
    df["Distancia (km)"] = [round(haversine_km(lat, lon, a, b), 2) for a, b in zip(df["Latitud"], df["Longitud"])]
    df = df[df["Distancia (km)"] <= radio_km]
    # Las estaciones SIATA suelen estar también en el catálogo (como AMVA): se deja la del catálogo.
    es_siata = df["Entidad"] == "SIATA"
    otras = df[~es_siata]
    duplicada = [
        s and any(haversine_km(a, b, c, d) < 0.15 for c, d in zip(otras["Latitud"], otras["Longitud"]))
        for s, a, b in zip(es_siata, df["Latitud"], df["Longitud"])
    ]
    df = df[[not x for x in duplicada]].sort_values("Distancia (km)")
    ideam = df["Entidad"] == "IDEAM"
    df = pd.concat([df[ideam].head(n_ideam), df[~ideam].head(n_otras)]).sort_values("Distancia (km)")
    columnas = ["Código", "Nombre", "Entidad", "Categoría", "Tecnología", "Departamento", "Municipio",
                "Latitud", "Longitud", "Elevación (msnm)", "Distancia (km)", "Instalada", "Dónde obtener los datos"]
    return df[columnas].reset_index(drop=True)
