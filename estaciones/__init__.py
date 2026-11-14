"""Módulo 1: búsqueda espacial y descarga de series de precipitación diaria.

Para agregar una fuente nueva (SIATA, Cornare, CVC, ...): crear un módulo que
implemente `FuentePluviometrica` (ver base.py) y pasarlo al `BuscadorEstaciones`.
"""

from .base import COLUMNAS_SERIE, Estacion, FuentePluviometrica
from .buscador import BuscadorEstaciones, ResultadoBusqueda
from .ideam import FuenteIDEAM

__all__ = [
    "COLUMNAS_SERIE",
    "BuscadorEstaciones",
    "Estacion",
    "FuenteIDEAM",
    "FuentePluviometrica",
    "ResultadoBusqueda",
]
