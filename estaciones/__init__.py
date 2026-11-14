"""Módulo 1: búsqueda espacial y descarga de series de precipitación diaria.

Para agregar una fuente nueva (SIATA, Cornare, CVC, ...): crear un módulo que
implemente `FuentePluviometrica` (ver base.py) y pasarlo al `BuscadorEstaciones`.
"""

try:
    # Usa el almacén de certificados del sistema operativo (en Windows completa las
    # cadenas incompletas que envían algunos servidores, p. ej. marco.cornare.gov.co).
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

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
