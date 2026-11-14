"""Conector con MARCO (Cornare): https://marco.cornare.gov.co

API REST abierta (sin autenticación), verificada el 2026-11-14:
  GET /api/v1/estaciones/                     75 estaciones; 32 con sensor "precipitacion"
  GET /api/v1/estaciones/{cod}/precipitacion?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
        -> {"count", "next", "values": [{"fecha", "muestra", "calidad", ...}]}, orden descendente,
           ~10.000 registros por página, "hasta" excluyente.
  GET /api/v1/municipios/

La resolución varía por estación (5 min u horaria); se suma a días calendario con el
mismo criterio de cobertura que el IDEAM. La historia es corta (desde ~2025).
Las fechas vienen marcadas como UTC ("Z") pero corresponden a la hora local.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging

import pandas as pd

from .base import Estacion, FuentePluviometrica, diaria_desde_subdiaria
from .red import ClienteJSON

log = logging.getLogger(__name__)

URL = "https://marco.cornare.gov.co/api/v1"


class FuenteCornare(FuentePluviometrica):
    nombre = "CORNARE"

    def __init__(self, cobertura_minima: float = 0.8):
        self.cliente = ClienteJSON(timeout_s=90)
        self.cobertura_minima = cobertura_minima

    def catalogo(self) -> list[Estacion]:
        municipios = {m["id"]: m["nombre"] for m in self.cliente.get(f"{URL}/municipios/")["values"]}
        datos = self.cliente.get(f"{URL}/estaciones/")
        estaciones = []
        for e in datos["values"] if isinstance(datos, dict) else datos:
            if "precipitacion" not in (e.get("sensores") or {}):
                continue
            estaciones.append(
                Estacion(
                    codigo=str(e["codigo"]),
                    nombre=(e.get("label") or e.get("ubicacion_campo") or "").strip(),
                    fuente=self.nombre,
                    entidad="CORNARE",
                    categoria=f"Red {e.get('red', '')}".strip(),
                    tecnologia="Automática",
                    estado="Activa",
                    departamento="Antioquia",
                    municipio=municipios.get(e.get("municipio"), ""),
                    latitud=float(e["latitud"]),
                    longitud=float(e["longitud"]),
                )
            )
        log.info("MARCO (Cornare): %d estaciones con sensor de precipitación", len(estaciones))
        return estaciones

    def _url(self, e: Estacion) -> str:
        return f"{URL}/estaciones/{e.codigo}/precipitacion"

    def ultima_fecha_con_datos(self, estacion: Estacion, desde: date) -> date | None:
        manana = (date.today() + timedelta(days=1)).isoformat()
        d = self.cliente.get(self._url(estacion), {"desde": desde.isoformat(), "hasta": manana})
        if d["values"]:  # orden descendente: el primero es el más reciente
            return date.fromisoformat(d["values"][0]["fecha"][:10])
        estacion.extra["motivo"] = f"sin datos de precipitación desde {desde}"
        return None

    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        params = {"desde": desde.isoformat(), "hasta": (hasta + timedelta(days=1)).isoformat()}
        url, valores = self._url(estacion), []
        while url:
            d = self.cliente.get(url, params)
            valores += d["values"]
            url, params = d.get("next"), None  # "next" ya trae los parámetros
        obs = pd.DataFrame(
            {
                "fecha_hora": pd.to_datetime([v["fecha"][:19] for v in valores]),
                "valor": pd.to_numeric([v["muestra"] for v in valores], errors="coerce"),
            }
        )
        obs = obs[obs["valor"] >= 0]
        return diaria_desde_subdiaria(obs, self.cobertura_minima)
