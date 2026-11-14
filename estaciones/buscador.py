"""Motor espacial: dado un punto, encuentra las N estaciones activas más cercanas
que realmente tienen datos de precipitación y descarga sus series diarias.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
import logging

import pandas as pd

from .base import Estacion, FuentePluviometrica
from .geo import haversine_km

log = logging.getLogger(__name__)


@dataclass
class ResultadoBusqueda:
    latitud: float
    longitud: float
    estaciones: list[Estacion]
    descartadas: list[tuple[Estacion, str]] = field(default_factory=list)
    series: dict[str, pd.DataFrame] = field(default_factory=dict)  # codigo -> fecha, precipitacion_mm
    resumen: pd.DataFrame | None = None


def estadisticas_serie(serie: pd.DataFrame) -> dict:
    """Periodo de registro, días con dato y % de faltantes de una serie diaria completa."""
    validos = serie.dropna(subset=["precipitacion_mm"])
    if validos.empty:
        return {"fecha_inicio": None, "fecha_fin": None, "total_registros": 0, "pct_faltantes": 100.0}
    inicio, fin = validos["fecha"].min(), validos["fecha"].max()
    dias_periodo = (fin - inicio).days + 1
    return {
        "fecha_inicio": inicio.date(),
        "fecha_fin": fin.date(),
        "total_registros": len(validos),
        "pct_faltantes": round(100 * (1 - len(validos) / dias_periodo), 2),
    }


class BuscadorEstaciones:
    def __init__(self, fuentes: list[FuentePluviometrica]):
        if not fuentes:
            raise ValueError("Se necesita al menos una fuente de datos.")
        self.fuentes = {f.nombre: f for f in fuentes}
        self.fuentes_caidas: list[str] = []

    # ------------------------------------------------------------------ búsqueda
    def candidatas(self, lat: float, lon: float) -> list[Estacion]:
        """Estaciones de todas las fuentes, ordenadas por distancia al punto."""
        todas: dict[tuple[str, str], Estacion] = {}
        for fuente in self.fuentes.values():
            try:
                catalogo = fuente.catalogo()
            except Exception as err:  # noqa: BLE001 - una fuente caída no debe frenar las demás
                log.warning("Fuente %s no disponible (%s); se continúa sin ella.", fuente.nombre, err)
                self.fuentes_caidas.append(fuente.nombre)
                continue
            for e in catalogo:
                e.distancia_km = round(haversine_km(lat, lon, e.latitud, e.longitud), 3)
                todas[(fuente.nombre, e.codigo)] = e
        return sorted(todas.values(), key=lambda e: e.distancia_km)

    def buscar(
        self,
        lat: float,
        lon: float,
        n: int = 5,
        max_dias_sin_datos: int = 365,
        max_verificaciones: int = 400,
        hilos: int = 8,
    ) -> ResultadoBusqueda:
        """Verifica candidatas en orden de distancia hasta confirmar `n` con datos.

        Una estación se confirma si tiene registros de precipitación y el último es de
        hace menos de `max_dias_sin_datos` días (activa en la práctica, no solo en el catálogo).
        """
        candidatas = self.candidatas(lat, lon)
        log.info("%d candidatas en el catálogo; verificando datos de las más cercanas...", len(candidatas))
        limite = date.today() - timedelta(days=max_dias_sin_datos)
        confirmadas: list[Estacion] = []
        descartadas: list[tuple[Estacion, str]] = []

        def verificar(e: Estacion) -> tuple[Estacion, str | None]:
            try:
                e.fecha_ultimo_dato = self.fuentes[e.fuente].ultima_fecha_con_datos(e, limite)
            except Exception as err:  # noqa: BLE001
                return e, f"no se pudo verificar (error/tiempo de espera de la API): {err}"
            if e.fecha_ultimo_dato is None:
                return e, e.extra.get("motivo", f"sin datos de precipitación desde {limite}")
            return e, None

        # Se verifica por tandas para no hacer consultas de más.
        pendientes = candidatas[:max_verificaciones]
        with ThreadPoolExecutor(max_workers=hilos) as pool:
            while pendientes and len(confirmadas) < n:
                tanda, pendientes = pendientes[:hilos], pendientes[hilos:]
                for e, motivo in pool.map(verificar, tanda):  # map conserva el orden de distancia
                    if motivo is None:
                        confirmadas.append(e)
                    else:
                        descartadas.append((e, motivo))

        if len(confirmadas) < n:
            log.warning("Solo se confirmaron %d de %d estaciones con datos.", len(confirmadas), n)
        return ResultadoBusqueda(lat, lon, confirmadas[:n], descartadas)

    # ------------------------------------------------------------------ descarga
    def descargar_series(self, resultado: ResultadoBusqueda, desde: date, hasta: date | None = None) -> None:
        """Descarga las series y arma la tabla resumen dentro de `resultado`."""
        hasta = hasta or date.today() - timedelta(days=1)  # el día en curso siempre está incompleto
        filas = []
        for e in resultado.estaciones:
            log.info("Descargando %s (%s), %.1f km...", e.codigo, e.nombre, e.distancia_km)
            crudo = self.fuentes[e.fuente].serie_diaria(e, desde, hasta)
            serie = crudo[["fecha", "precipitacion_mm"]]
            # Calendario completo entre el primer y el último día con dato; los
            # faltantes quedan vacíos (NaN) para que el hueco sea visible.
            validos = serie.dropna()
            if not validos.empty:
                dias = pd.date_range(validos["fecha"].min(), validos["fecha"].max(), freq="D")
                serie = serie.set_index("fecha").reindex(dias).rename_axis("fecha").reset_index()
            resultado.series[e.codigo] = serie
            est = estadisticas_serie(serie)
            filas.append(
                {
                    "Código": e.codigo,
                    "Nombre": e.nombre,
                    "Entidad": e.entidad,
                    "Fuente": e.fuente,
                    "Categoría": e.categoria,
                    "Tecnología": e.tecnologia,
                    "Estado": e.estado,
                    "Departamento": e.departamento,
                    "Municipio": e.municipio,
                    "Latitud": e.latitud,
                    "Longitud": e.longitud,
                    "Elevación (msnm)": e.elevacion_msnm,
                    "Distancia (km)": round(e.distancia_km, 2),
                    "Fecha inicio": est["fecha_inicio"],
                    "Fecha fin": est["fecha_fin"],
                    "Total registros (días)": est["total_registros"],
                    "% faltantes": est["pct_faltantes"],
                    "Último dato en fuente": e.fecha_ultimo_dato,
                }
            )
        resultado.resumen = pd.DataFrame(filas)
