"""Conector con Piragua (Corantioquia): https://piragua.corantioquia.gov.co

API REST abierta (sin autenticación), verificada el 2026-11-14:
  GET /api/v1/estaciones/?tipo=1                       pluviógrafos (85)
  GET /api/v1/estaciones/?tipo=8                       estaciones meteorológicas (22), incluyen lluvia
  GET /api/v1/estaciones/{cod}/precipitacion/diario/?fecha__gte=&fecha__lt=   campo "muestra"
  GET /api/v1/estaciones/{cod}/meteorologia/diario/?fecha__gte=&fecha__lt=    campo "lluvia"
  GET /api/v1/municipios/

Los valores diarios traen "porc_datos" (% de datos del día). Se pagina de a 31
registros; los campos "calidad" no están documentados, así que no se usan para filtrar.
Las fechas vienen marcadas como UTC ("Z") pero corresponden a la hora local.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import logging
import math

import pandas as pd

from .base import COLUMNAS_SERIE, Estacion, FuentePluviometrica
from .red import ClienteJSON

log = logging.getLogger(__name__)

URL = "https://piragua.corantioquia.gov.co/api/v1"
TIPOS = {1: ("precipitacion", "muestra"), 8: ("meteorologia", "lluvia")}


class FuentePiragua(FuentePluviometrica):
    nombre = "PIRAGUA"

    def __init__(self, hilos: int = 4, cobertura_minima: float = 0.8):
        self.cliente = ClienteJSON()
        self.hilos = hilos
        self.cobertura_minima = cobertura_minima

    def catalogo(self) -> list[Estacion]:
        municipios = {m["id"]: m["nombre"] for m in self.cliente.get(f"{URL}/municipios/")["values"]}
        estaciones = []
        for tipo in TIPOS:
            for e in self.cliente.get(f"{URL}/estaciones/", {"tipo": tipo})["values"]:
                if not e.get("activo"):
                    continue
                estaciones.append(
                    Estacion(
                        codigo=str(e["codigo"]),
                        nombre=f"{e.get('ubicacion') or ''} ({e.get('fuente') or ''})".strip(" ()"),
                        fuente=self.nombre,
                        entidad="CORANTIOQUIA",
                        categoria=e.get("tipo_nombre", ""),
                        tecnologia="Automática",
                        estado="Activa",
                        departamento="Antioquia",
                        municipio=municipios.get(e.get("municipio"), ""),
                        latitud=float(e["latitud"]),
                        longitud=float(e["longitud"]),
                        elevacion_msnm=e.get("altitud"),
                        extra={"tipo": tipo},
                    )
                )
        log.info("Piragua (Corantioquia): %d estaciones activas con lluvia", len(estaciones))
        return estaciones

    def _url_diaria(self, e: Estacion) -> tuple[str, str]:
        recurso, campo = TIPOS[e.extra["tipo"]]
        return f"{URL}/estaciones/{e.codigo}/{recurso}/diario/", campo

    def ultima_fecha_con_datos(self, estacion: Estacion, desde: date) -> date | None:
        url, campo = self._url_diaria(estacion)
        inicio = max(desde, date.today() - timedelta(days=45))
        for a in dict.fromkeys([inicio, desde]):
            d = self.cliente.get(url, {"fecha__gte": a.isoformat(), "fecha__lt": (date.today() + timedelta(days=1)).isoformat()})
            # Días vacíos llegan como 0 mm con porc_datos 0: se exige la cobertura mínima.
            fechas = [
                v["fecha"][:10]
                for v in d["values"]
                if float(v.get(campo) or -999) >= 0 and float(v.get("porc_datos") or 0) >= 100 * self.cobertura_minima
            ]
            if fechas:  # la API ordena de la más reciente a la más antigua
                return date.fromisoformat(max(fechas))
        estacion.extra["motivo"] = f"sin datos de lluvia desde {desde}"
        return None

    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        url, campo = self._url_diaria(estacion)
        params = {"fecha__gte": desde.isoformat(), "fecha__lt": (hasta + timedelta(days=1)).isoformat()}
        primera = self.cliente.get(url, params)
        por_pagina = max(len(primera["values"]), 1)
        paginas = math.ceil(primera["count"] / por_pagina)
        with ThreadPoolExecutor(max_workers=self.hilos) as pool:
            resto = pool.map(lambda p: self.cliente.get(url, {**params, "page": p})["values"], range(2, paginas + 1))
            valores = primera["values"] + [v for pag in resto for v in pag]
        if not valores:
            return pd.DataFrame(columns=COLUMNAS_SERIE)

        df = pd.DataFrame(valores)
        df["fecha"] = pd.to_datetime(df["fecha"].str[:10])
        df["precipitacion_mm"] = pd.to_numeric(df[campo], errors="coerce").round(2)
        df["porc"] = pd.to_numeric(df["porc_datos"], errors="coerce")
        df = df.drop_duplicates(subset="fecha").sort_values("fecha").reset_index(drop=True)
        invalido = (df["precipitacion_mm"] < 0) | (df["porc"] < 100 * self.cobertura_minima)
        df.loc[invalido, "precipitacion_mm"] = float("nan")
        df["n_registros"] = 0  # la fuente entrega el % de datos, no el conteo
        return df[COLUMNAS_SERIE]
