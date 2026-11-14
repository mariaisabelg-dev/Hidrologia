"""Conector en tiempo real con los datos abiertos del IDEAM en www.datos.gov.co.

Datasets usados (verificados el 2026-11-13):
  - hp9r-jxuu  "Catálogo Nacional de Estaciones del IDEAM" (CNE): metadatos y estado
    de todas las estaciones del país (IDEAM y otras entidades).
  - s54a-sgyg  "Precipitación": observaciones cada 10 min de las estaciones
    AUTOMÁTICAS del IDEAM (desde ~2003), actualizadas varias veces al día.

Limitaciones conocidas (ver docs/fuentes_datos.md):
  - Las estaciones convencionales (lectura manual diaria) no publican series en
    datos.gov.co; sus datos están en DHIME, que no tiene API abierta. Por eso aquí
    solo se consideran candidatas las estaciones con tecnología automática.
  - s54a-sgyg trae cada observación DUPLICADA. Se deduplica en el servidor
    agrupando por fecha de observación antes de sumar.
  - Agregar toda la historia de una estación en una sola consulta supera el tiempo
    límite del servidor, así que se descarga en bloques de 6 meses en paralelo.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import logging

import pandas as pd
import requests

from .base import Estacion, FuentePluviometrica, marcar_dias_incompletos
from .socrata import ClienteSocrata

log = logging.getLogger(__name__)

DS_CATALOGO = "hp9r-jxuu"
DS_PRECIPITACION = "s54a-sgyg"

# Categorías del CNE que incluyen medición de precipitación.
CATEGORIAS_CON_PRECIPITACION = (
    "Pluviométrica",
    "Pluviográfica",
    "Climatológica Principal",
    "Climatológica Ordinaria",
    "Agrometeorológica",
    "Sinóptica Principal",
    "Sinóptica Secundaria",
    "Meteorológica Especial",
    "HidroMeteorológica",
)

DS_TIEMPO_REAL = "57sv-p2fu"  # "Datos de Estaciones de IDEAM y de Terceros": últimas ~12 h

# Sigla por palabra clave (algunos nombres llegan con la codificación dañada desde la fuente).
SIGLAS_ENTIDAD = [
    ("HIDROLOG", "IDEAM"),
    ("GESTI", "IDIGER"),  # Instituto Distrital de Gestión de Riesgos y Cambio Climático
    ("FOPAE", "FOPAE"),
    ("ISAG", "ISAGEN"),
    ("PARQUES NACIONALES", "PNN"),
    ("ACUEDUCTO Y ALCANTARILLADO DE BOGOT", "EAAB"),
    ("VALLE DEL CAUCA", "CVC"),
    ("QUIND", "CRQ"),
    ("REGIONAL DE SANTANDER", "CAS"),
    ("REGIONAL DE CUNDINAMARCA", "CAR"),
    ("REGIONAL DE ANTIOQUIA", "CORANTIOQUIA"),
    ("RIOS NEGRO Y NARE", "CORNARE"),
    ("METROPOLITANA DEL VALLE DE ABURR", "AMVA"),
    ("EMPRESAS PÚBLICAS DE MEDELL", "EPM"),
]


def sigla_entidad(nombre: str) -> str:
    n = (nombre or "").upper()
    for clave, sigla in SIGLAS_ENTIDAD:
        if clave in n:
            return sigla
    return nombre or ""


def _float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def normalizar_codigo(codigo: str) -> str:
    """El catálogo trae el mismo código con y sin ceros iniciales ('27011270' y '0027011270').
    Se usa la forma de 10 dígitos, que es la de las series de datos."""
    codigo = (codigo or "").strip()
    return codigo.zfill(10) if codigo.isdigit() else codigo


def _bloques(desde: date, hasta: date, meses: int = 6) -> list[tuple[date, date]]:
    """Intervalos semiabiertos [a, b) de `meses` meses que cubren [desde, hasta]."""
    out, a = [], date(desde.year, desde.month, 1)
    fin = hasta + timedelta(days=1)
    while a < fin:
        m = a.month - 1 + meses
        b = date(a.year + m // 12, m % 12 + 1, 1)
        out.append((a, min(b, fin)))
        a = b
    return out


class FuenteIDEAM(FuentePluviometrica):
    nombre = "IDEAM"

    def __init__(
        self,
        cliente: ClienteSocrata | None = None,
        hilos: int = 6,
        cobertura_minima: float = 0.8,
    ):
        """
        hilos: peticiones simultáneas al descargar una serie.
        cobertura_minima: fracción mínima de observaciones de 10 min que debe tener un
            día para considerar válida su suma de 24 h (si no, queda como faltante).
        """
        self.cliente = cliente or ClienteSocrata()
        self.hilos = hilos
        self.cobertura_minima = cobertura_minima
        self.bloques_fallidos: list[tuple[str, date, date]] = []

    # ------------------------------------------------------------------ catálogo
    def catalogo(self) -> list[Estacion]:
        categorias = ", ".join(f"'{c}'" for c in CATEGORIAS_CON_PRECIPITACION)
        filas = self.cliente.consultar(
            DS_CATALOGO,
            {
                "$select": "codigo, nombre, categoria, tecnologia, estado, departamento, municipio, "
                "latitud, longitud, altitud, entidad, fecha_instalacion",
                "$where": f"estado = 'Activa' AND tecnologia like '%Autom%' AND categoria in ({categorias})",
                "$limit": 50000,
            },
        )
        estaciones: dict[str, Estacion] = {}
        for f in filas:  # el catálogo trae filas repetidas: se deja una por código
            lat, lon = _float(f.get("latitud")), _float(f.get("longitud"))
            codigo = normalizar_codigo(f.get("codigo"))
            if codigo in estaciones or lat is None or lon is None:
                continue
            estaciones[codigo] = Estacion(
                codigo=codigo,
                nombre=f.get("nombre", ""),
                fuente=self.nombre,
                entidad=sigla_entidad(f.get("entidad", "")),
                categoria=f.get("categoria", ""),
                tecnologia=f.get("tecnologia", ""),
                estado=f.get("estado", ""),
                departamento=f.get("departamento", ""),
                municipio=f.get("municipio", ""),
                latitud=lat,
                longitud=lon,
                elevacion_msnm=_float(f.get("altitud")),
                extra={"fecha_instalacion": f.get("fecha_instalacion")},
            )
        n_catalogo = len(estaciones)

        # Estaciones de terceros (IDIGER, FOPAE, ISAGEN, PNN…) que transmiten lluvia
        # por el sistema del IDEAM pero pueden no estar marcadas así en el catálogo.
        try:
            terceros = self.cliente.consultar(
                DS_TIEMPO_REAL,
                {
                    "$query": "SELECT codigoestacion, nombreestacion, entidad, departamento, municipio, "
                    "max(latitud) AS lat, max(longitud) AS lon WHERE codigosensor = '0240' "
                    "GROUP BY codigoestacion, nombreestacion, entidad, departamento, municipio LIMIT 5000"
                },
                timeout_s=90,
            )
        except Exception as e:  # noqa: BLE001 - es un complemento; no debe frenar la búsqueda
            log.warning("No se pudo consultar %s (estaciones de terceros): %s", DS_TIEMPO_REAL, e)
            terceros = []
        for f in terceros:
            lat, lon = _float(f.get("lat")), _float(f.get("lon"))
            codigo = normalizar_codigo(f["codigoestacion"])
            if codigo in estaciones or lat is None or lon is None:
                continue
            estaciones[codigo] = Estacion(
                codigo=codigo,
                nombre=f.get("nombreestacion", ""),
                fuente=self.nombre,
                entidad=sigla_entidad(f.get("entidad", "")),
                categoria="",
                tecnologia="Automática (transmite en tiempo real)",
                estado="Activa",
                departamento=f.get("departamento", ""),
                municipio=f.get("municipio", ""),
                latitud=lat,
                longitud=lon,
            )
        log.info("IDEAM (datos.gov.co): %d estaciones del catálogo + %d de terceros en tiempo real",
                 n_catalogo, len(estaciones) - n_catalogo)
        return list(estaciones.values())

    # -------------------------------------------------------------- verificación
    # Nota de rendimiento (medido 2026-11-13): "ORDER BY fecha DESC LIMIT 1" a veces
    # responde en 4 s y a veces supera 150 s, y nunca termina si la estación no está
    # en el dataset. Por eso se verifica en dos pasos con consultas acotadas.
    def ultima_fecha_con_datos(self, estacion: Estacion, desde: date) -> date | None:
        cod = estacion.codigo
        # 1) ¿Publica algún dato? (sin ORDER BY: ~4 s, exista o no)
        existe = self.cliente.consultar(
            DS_PRECIPITACION,
            {"$select": "fechaobservacion", "$where": f"codigoestacion = '{cod}'", "$limit": 1},
            timeout_s=60,
        )
        if not existe:
            estacion.extra["motivo"] = "la estación no publica precipitación en datos.gov.co (s54a-sgyg)"
            return None
        # 2) Último dato: primero en los últimos 30 días; si no hay, hasta `desde`.
        ventanas = [max(desde, date.today() - timedelta(days=30)), desde]
        for inicio in dict.fromkeys(ventanas):
            filas = self.cliente.consultar(
                DS_PRECIPITACION,
                {
                    "$select": "max(fechaobservacion) AS ultima",
                    "$where": f"codigoestacion = '{cod}' AND fechaobservacion >= '{inicio.isoformat()}T00:00:00'",
                },
                timeout_s=90,
            )
            if filas and filas[0].get("ultima"):
                return datetime.fromisoformat(filas[0]["ultima"]).date()
        estacion.extra["motivo"] = f"sin datos desde {desde} (tiene registros más antiguos)"
        return None

    # ------------------------------------------------------------------- series
    def _consulta_bloque(self, codigo: str, a: date, b: date) -> list[dict]:
        # 1) agrupa por instante para eliminar duplicados; 2) suma por día calendario.
        q = (
            "SELECT fechaobservacion, max(valorobservado) AS v "
            f"WHERE codigoestacion = '{codigo}' "
            f"AND fechaobservacion >= '{a.isoformat()}T00:00:00' "
            f"AND fechaobservacion < '{b.isoformat()}T00:00:00' "
            "GROUP BY fechaobservacion "
            "|> SELECT date_trunc_ymd(fechaobservacion) AS dia, sum(v) AS p, count(*) AS n "
            "GROUP BY dia ORDER BY dia LIMIT 1000"
        )
        return self.cliente.consultar(DS_PRECIPITACION, {"$query": q})

    def _bloque(self, codigo: str, a: date, b: date) -> list[dict]:
        """Descarga un bloque; si el servidor se demora demasiado lo parte en dos."""
        try:
            return self._consulta_bloque(codigo, a, b)
        except requests.Timeout:
            if (b - a).days > 35:
                medio = a + (b - a) / 2
                log.debug("Timeout en %s %s–%s: se divide el bloque", codigo, a, b)
                return self._bloque(codigo, a, medio) + self._bloque(codigo, medio, b)
            try:
                return self._consulta_bloque(codigo, a, b)
            except Exception as e:  # noqa: BLE001
                log.warning("No se pudo descargar %s entre %s y %s: %s", codigo, a, b, e)
                self.bloques_fallidos.append((codigo, a, b))
                return []

    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        bloques = _bloques(desde, hasta)
        with ThreadPoolExecutor(max_workers=self.hilos) as pool:
            partes = pool.map(lambda ab: self._bloque(estacion.codigo, *ab), bloques)
            filas = [f for parte in partes for f in parte]

        if not filas:
            return pd.DataFrame(columns=["fecha", "precipitacion_mm", "n_registros"])

        df = pd.DataFrame(filas)
        df["fecha"] = pd.to_datetime(df["dia"]).dt.normalize()
        df["precipitacion_mm"] = df["p"].astype(float)
        df["n_registros"] = df["n"].astype(int)
        return marcar_dias_incompletos(df, self.cobertura_minima)
