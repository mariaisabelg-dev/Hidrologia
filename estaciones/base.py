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
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# Columnas de la serie diaria que toda fuente debe devolver.
#   fecha            -> datetime64 (día calendario, hora local de Colombia)
#   precipitacion_mm -> float; NaN si el día no tiene dato válido
#   n_registros      -> int; observaciones crudas que componen el día (0 si no es aplicable)
COLUMNAS_SERIE = ["fecha", "precipitacion_mm", "n_registros"]


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

    @abstractmethod
    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        """Serie de precipitación diaria (24 h) con las columnas de COLUMNAS_SERIE.

        Solo debe incluir días con información (los faltantes se completan después).
        """
