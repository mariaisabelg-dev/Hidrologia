"""Contrato común para todas las fuentes de datos pluviométricos.

Cada fuente (IDEAM, SIATA, Cornare, CVC, ...) implementa `FuentePluviometrica`
y entrega:
  - Metadatos de estaciones como objetos `Estacion`.
  - Series diarias como DataFrame con las columnas de `COLUMNAS_SERIE`.

El buscador y los exportadores solo conocen este contrato, así que agregar una
fuente nueva no requiere tocar el resto del código.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import calendar
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# Columnas de la serie diaria que toda fuente debe devolver.
#   fecha            -> datetime64 (día calendario, hora local de Colombia)
#   precipitacion_mm -> float; NaN si el día no tiene dato válido
#   n_registros      -> int; observaciones crudas que componen el día (0 si no es aplicable)
COLUMNAS_SERIE = ["fecha", "precipitacion_mm", "n_registros"]


def diaria_desde_subdiaria(obs: pd.DataFrame, cobertura_minima: float) -> pd.DataFrame:
    """Suma observaciones sub-diarias (columnas fecha_hora, valor) a días calendario.

    Un día es válido si tiene al menos `cobertura_minima` de las observaciones
    esperadas. Las esperadas por día son la moda de cada año (144 si el registro es
    cada 10 min, 288 si cada 5 min, 24 si horario…), así se adapta a cada estación.
    Elimina instantes duplicados antes de sumar.
    """
    if obs.empty:
        return pd.DataFrame(columns=COLUMNAS_SERIE)
    obs = obs.drop_duplicates(subset="fecha_hora")
    dia = obs["fecha_hora"].dt.normalize()
    df = obs.groupby(dia)["valor"].agg(precipitacion_mm="sum", n_registros="count")
    df = df.rename_axis("fecha").reset_index()
    return marcar_dias_incompletos(df, cobertura_minima)


def marcar_dias_incompletos(df: pd.DataFrame, cobertura_minima: float) -> pd.DataFrame:
    """Deja en NaN la precipitación de días con pocas observaciones (ver diaria_desde_subdiaria)."""
    df = df.sort_values("fecha").reset_index(drop=True)
    esperadas = df.groupby(df["fecha"].dt.year)["n_registros"].transform(lambda s: s.mode().max())
    df["precipitacion_mm"] = df["precipitacion_mm"].astype(float).round(2)
    df.loc[df["n_registros"] / esperadas < cobertura_minima, "precipitacion_mm"] = float("nan")
    return df[COLUMNAS_SERIE]


def anios_completos(serie: pd.DataFrame, cobertura_anual: float) -> int:
    """Años calendario con al menos `cobertura_anual` de sus días con dato válido.

    Es la medida de longitud de registro que usa la selección: un año con muchos
    huecos no sirve para análisis de máximos anuales, así que no cuenta.
    """
    validos = serie.dropna(subset=["precipitacion_mm"])
    if validos.empty:
        return 0
    por_anio = validos.groupby(validos["fecha"].dt.year).size()
    dias = pd.Series([366 if calendar.isleap(a) else 365 for a in por_anio.index], index=por_anio.index)
    return int((por_anio / dias >= cobertura_anual).sum())


@dataclass
class Estacion:
    """Metadatos estandarizados de una estación pluviométrica."""

    codigo: str
    nombre: str
    fuente: str  # conector que la provee, p. ej. "IDEAM"
    entidad: str  # entidad propietaria/operadora según el catálogo
    categoria: str
    tecnologia: str
    estado: str
    departamento: str
    municipio: str
    latitud: float
    longitud: float
    elevacion_msnm: float | None = None
    # Se llenan durante la búsqueda / descarga:
    distancia_km: float | None = None
    fecha_ultimo_dato: date | None = None
    extra: dict = field(default_factory=dict)


class FuentePluviometrica(ABC):
    """Interfaz que debe implementar cada conector de datos."""

    #: Nombre corto de la fuente (aparece en las salidas).
    nombre: str = "SIN_NOMBRE"

    @abstractmethod
    def catalogo(self) -> list[Estacion]:
        """Estaciones activas que miden precipitación (sin verificar datos aún)."""

    @abstractmethod
    def ultima_fecha_con_datos(self, estacion: Estacion, desde: date) -> date | None:
        """Fecha del registro más reciente de precipitación posterior a `desde`, o None.

        Debe ser una consulta liviana: se usa para descartar candidatas sin datos
        antes de descargar series completas. Si devuelve None, puede dejar la causa
        en `estacion.extra["motivo"]`.
        """

    def tiene_datos_antes(self, estacion: Estacion, fecha: date) -> bool | None:
        """¿Hay registros anteriores a `fecha`? Filtro rápido de longitud de registro.

        None = no se sabe (la fuente no lo permite o la consulta no respondió a
        tiempo); en ese caso la decisión se toma después de descargar la serie.
        """
        return None

    @abstractmethod
    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        """Serie de precipitación diaria (24 h) con las columnas de COLUMNAS_SERIE.

        Solo debe incluir días con información (los faltantes se completan después).
        """
