"""Fuente semiautomática: archivos descargados a mano de DHIME (IDEAM).

Flujo:
  1. El programa escoge las estaciones del IDEAM cercanas (hoja "Seleccionadas") sin
     descarga automática y los rangos de años a pedir en DHIME (máximo 29 años por
     descarga, así que una estación larga puede necesitar varios archivos).
  2. El usuario descarga los CSV y los deja en datos/crudos/ (cualquier nombre,
     subcarpetas permitidas).
  3. En la siguiente ejecución esta fuente lee todos los CSV de DHIME, une los
     archivos de cada estación (sin importar cuántos sean ni si se traslapan) y la
     estación compite con las demás en la selección.

Formato del CSV de DHIME (verificado 2026-11-14):
  CodigoEstacion,NombreEstacion,Variable,Parametro,Fecha,Unidad,Valor,NivelAprobacion
  26180160,ABEJORRAL [26180160],PRECIPITACION,Día pluviométrico (convencional),1971-01-01 00:00,mm,0,Definitivo

El "día pluviométrico" del IDEAM en estaciones convencionales va de 7:00 a 7:00
(lectura del pluviómetro a las 7 de la mañana) y se rotula con la fecha de la lectura.
"""

from __future__ import annotations

from datetime import date
import logging
from pathlib import Path

import pandas as pd

from .base import COLUMNAS_SERIE, Estacion, FuentePluviometrica
from .ideam import normalizar_codigo

log = logging.getLogger(__name__)

COLUMNAS_DHIME = {"CodigoEstacion", "NombreEstacion", "Variable", "Parametro", "Fecha", "Valor"}
PRIORIDAD_APROBACION = {"Definitivo": 0, "Preliminar": 1}


def _leer_csv(ruta: Path) -> pd.DataFrame | None:
    """Lee un CSV si tiene el formato de DHIME; si no, devuelve None."""
    for sep in (",", ";"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(ruta, sep=sep, encoding=enc, dtype=str)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
            if COLUMNAS_DHIME <= set(df.columns):
                df["archivo"] = ruta.name
                return df
    return None


def leer_archivos_dhime(carpeta: Path) -> pd.DataFrame:
    """Precipitación diaria de todos los CSV de DHIME bajo `carpeta`, unida por estación.

    Columnas: codigo, nombre, fecha, precipitacion_mm, aprobacion, archivo.
    Si un día aparece en varios archivos se deja uno (primero 'Definitivo').
    """
    partes = []
    for ruta in sorted(carpeta.rglob("*.csv")):
        df = _leer_csv(ruta)
        if df is None:
            continue
        df = df[df["Variable"].str.upper().str.startswith("PRECIPITACI")]
        df = df[df["Parametro"].str.contains("pluviom", case=False, na=False)]  # total diario
        if df.empty:
            log.info("DHIME: %s no trae precipitación diaria; se omite.", ruta.name)
            continue
        partes.append(df)
    if not partes:
        return pd.DataFrame(columns=["codigo", "nombre", "fecha", "precipitacion_mm", "aprobacion", "archivo"])

    df = pd.concat(partes, ignore_index=True)
    out = pd.DataFrame(
        {
            "codigo": df["CodigoEstacion"].map(normalizar_codigo),
            "nombre": df["NombreEstacion"],
            "fecha": pd.to_datetime(df["Fecha"].str[:10], errors="coerce"),
            "precipitacion_mm": pd.to_numeric(df["Valor"].str.replace(",", "."), errors="coerce"),
            "aprobacion": df.get("NivelAprobacion", pd.Series("", index=df.index)).fillna(""),
            "archivo": df["archivo"],
        }
    ).dropna(subset=["fecha"])
    out = out[out["precipitacion_mm"].isna() | (out["precipitacion_mm"] >= 0)]
    out["_p"] = out["aprobacion"].map(PRIORIDAD_APROBACION).fillna(9)
    out = out.sort_values(["codigo", "fecha", "_p"]).drop_duplicates(["codigo", "fecha"]).drop(columns="_p")
    return out.reset_index(drop=True)


def periodos_cargados(datos: pd.DataFrame) -> dict[str, tuple[date, date, int]]:
    """codigo -> (primer día, último día, número de archivos)."""
    if datos.empty:
        return {}
    g = datos.dropna(subset=["precipitacion_mm"]).groupby("codigo")
    return {
        c: (d["fecha"].min().date(), d["fecha"].max().date(), d["archivo"].nunique())
        for c, d in g
    }


class FuenteDHIMEArchivos(FuentePluviometrica):
    nombre = "DHIME (archivo)"

    def __init__(self, carpeta: Path, catalogo_nacional: list[dict]):
        """catalogo_nacional: salida de ideam.catalogo_nacional(), para ubicar las estaciones."""
        self.carpeta = carpeta
        self.datos = leer_archivos_dhime(carpeta)
        self.periodos = periodos_cargados(self.datos)
        self.meta = {f["codigo"]: f for f in catalogo_nacional}

    def catalogo(self) -> list[Estacion]:
        estaciones = []
        for codigo, (inicio, fin, n_archivos) in self.periodos.items():
            m = self.meta.get(codigo)
            if m is None:
                log.warning("DHIME: la estación %s no está en el Catálogo Nacional; sin coordenadas, se omite.", codigo)
                continue
            estaciones.append(
                Estacion(
                    codigo=codigo,
                    nombre=m["nombre"],
                    fuente=self.nombre,
                    entidad=m["entidad"],
                    categoria=m["categoria"],
                    tecnologia=m["tecnologia"],
                    estado=m["estado"],
                    departamento=m["departamento"],
                    municipio=m["municipio"],
                    latitud=m["latitud"],
                    longitud=m["longitud"],
                    elevacion_msnm=m["altitud"],
                    extra={"archivos": n_archivos, "fecha_instalacion": m["instalacion"],
                           "fecha_suspension": m["suspension"]},
                )
            )
        if estaciones:
            log.info("DHIME (archivos en %s): %d estaciones cargadas", self.carpeta.name, len(estaciones))
        return estaciones

    def ultima_fecha_con_datos(self, estacion: Estacion, desde: date) -> date | None:
        fin = self.periodos[estacion.codigo][1]
        if fin < desde:
            estacion.extra["motivo"] = f"los archivos de DHIME cargados terminan en {fin}"
            return None
        return fin

    def tiene_datos_antes(self, estacion: Estacion, fecha: date) -> bool | None:
        return self.periodos[estacion.codigo][0] < fecha

    def serie_diaria(self, estacion: Estacion, desde: date, hasta: date) -> pd.DataFrame:
        d = self.datos[self.datos["codigo"] == estacion.codigo]
        d = d[(d["fecha"] >= pd.Timestamp(desde)) & (d["fecha"] <= pd.Timestamp(hasta))].copy()
        d["n_registros"] = 0
        return d[COLUMNAS_SERIE].reset_index(drop=True)
