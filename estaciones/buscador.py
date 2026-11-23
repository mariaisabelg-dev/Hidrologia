"""Motor espacial: dado un punto, encuentra las N estaciones más cercanas que
cumplen los criterios de selección (vigencia y longitud de registro) y descarga
sus series diarias en ese momento, desde cada fuente.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
import logging

import pandas as pd

from .base import Estacion, FuentePluviometrica, anios_completos
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
        """`fuentes` en orden de preferencia: si dos fuentes tienen la misma estación
        (mismo código), se usa la primera. Por eso DHIME (archivos) va primero."""
        if not fuentes:
            raise ValueError("Se necesita al menos una fuente de datos.")
        self.fuentes = {f.nombre: f for f in fuentes}
        self.fuentes_caidas: list[str] = []

    # ------------------------------------------------------------------ búsqueda
    def candidatas(self, lat: float, lon: float) -> list[Estacion]:
        """Estaciones de todas las fuentes, ordenadas por distancia al punto."""
        todas: dict[str, Estacion] = {}
        for fuente in self.fuentes.values():
            try:
                catalogo = fuente.catalogo()
            except Exception as err:  # noqa: BLE001 - una fuente caída no debe frenar las demás
                log.warning("Fuente %s no disponible (%s); se continúa sin ella.", fuente.nombre, err)
                self.fuentes_caidas.append(fuente.nombre)
                continue
            for e in catalogo:
                if e.codigo in todas:
                    continue
                e.distancia_km = round(haversine_km(lat, lon, e.latitud, e.longitud), 3)
                todas[e.codigo] = e
        return sorted(todas.values(), key=lambda e: e.distancia_km)

    def buscar(
        self,
        lat: float,
        lon: float,
        n: int = 5,
        fin_minimo: date = date(2000, 1, 1),
        min_anios: int = 10,
        cobertura_anual: float = 0.8,
        desde: date = date(1900, 1, 1),
        hasta: date | None = None,
        max_verificaciones: int = 400,
        hilos: int = 8,
    ) -> ResultadoBusqueda:
        """Selecciona las `n` estaciones más cercanas que cumplen los criterios y descarga sus series.

        Una candidata se acepta si:
          1. tiene datos posteriores a `fin_minimo` (no suspendida antes);
          2. tiene datos anteriores a hoy − `min_anios` (filtro rápido, antes de descargar);
          3. ya descargada, tiene al menos `min_anios` años completos (años con
             ≥ `cobertura_anual` de días con dato válido).
        Los pasos 1 y 2 se hacen por tandas en paralelo; la descarga, en orden de distancia.
        """
        hasta = hasta or date.today() - timedelta(days=1)  # el día en curso siempre está incompleto
        hoy = date.today()
        hace_n_anios = date(hoy.year - min_anios, hoy.month, 1)
        candidatas = self.candidatas(lat, lon)
        log.info("%d candidatas en los catálogos; verificando las más cercanas...", len(candidatas))
        res = ResultadoBusqueda(lat, lon, [])

        def verificar(e: Estacion) -> tuple[Estacion, str | None]:
            fuente = self.fuentes[e.fuente]
            try:
                e.fecha_ultimo_dato = fuente.ultima_fecha_con_datos(e, fin_minimo)
                if e.fecha_ultimo_dato is None:
                    return e, e.extra.get("motivo", f"sin datos de precipitación desde {fin_minimo}")
                if fuente.tiene_datos_antes(e, hace_n_anios) is False:
                    return e, f"registro de menos de {min_anios} años (sin datos antes de {hace_n_anios})"
            except Exception as err:  # noqa: BLE001
                return e, f"no se pudo verificar (error/tiempo de espera de la API): {err}"
            return e, None

        pendientes = candidatas[:max_verificaciones]
        with ThreadPoolExecutor(max_workers=hilos) as pool:
            while pendientes and len(res.estaciones) < n:
                tanda, pendientes = pendientes[:hilos], pendientes[hilos:]
                for e, motivo in pool.map(verificar, tanda):  # map conserva el orden de distancia
                    if len(res.estaciones) >= n:
                        break  # las que sobran de la tanda no se descargan
                    if motivo is not None:
                        res.descartadas.append((e, motivo))
                        continue
                    try:
                        serie = self._descargar(e, desde, hasta)
                    except Exception as err:  # noqa: BLE001 - una estación con error no frena las demás
                        res.descartadas.append((e, f"error al descargar la serie: {err}"))
                        continue
                    completos = anios_completos(serie, cobertura_anual)
                    e.extra["anios_completos"] = completos
                    if completos < min_anios:
                        est = estadisticas_serie(serie)
                        res.descartadas.append(
                            (e, f"solo {completos} años completos (≥ {cobertura_anual:.0%} de días con dato) "
                                f"entre {est['fecha_inicio']} y {est['fecha_fin']}; se exigen {min_anios}")
                        )
                        continue
                    res.estaciones.append(e)
                    res.series[e.codigo] = serie

        if len(res.estaciones) < n:
            log.warning("Solo %d de %d estaciones cumplen los criterios.", len(res.estaciones), n)
        res.resumen = self._resumen(res)
        return res

    # ------------------------------------------------------------------ descarga
    def _descargar(self, e: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        log.info("Descargando %s (%s, %s), %.1f km...", e.codigo, e.nombre, e.fuente, e.distancia_km)
        crudo = self.fuentes[e.fuente].serie_diaria(e, desde, hasta)
        serie = crudo[["fecha", "precipitacion_mm"]]
        # Calendario completo entre el primer y el último día con dato; los
        # faltantes quedan vacíos (NaN) para que el hueco sea visible.
        validos = serie.dropna()
        if not validos.empty:
            dias = pd.date_range(validos["fecha"].min(), validos["fecha"].max(), freq="D")
            serie = serie.set_index("fecha").reindex(dias).rename_axis("fecha").reset_index()
        return serie

    @staticmethod
    def _resumen(res: ResultadoBusqueda) -> pd.DataFrame:
        filas = []
        for e in res.estaciones:
            est = estadisticas_serie(res.series[e.codigo])
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
                    "Años completos": e.extra.get("anios_completos"),
                    "Último dato en fuente": e.fecha_ultimo_dato,
                }
            )
        return pd.DataFrame(filas)
