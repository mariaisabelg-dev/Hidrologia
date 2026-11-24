"""Escritura de entregables: Excel, shapefiles y series (Excel + CSV)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pandas as pd
import shapefile  # pyshp

WKT_WGS84 = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def _ajustar_hoja(ws, df: pd.DataFrame) -> None:
    ws.freeze_panes = "A2"
    for i, col in enumerate(df.columns, start=1):
        largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(500)])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(largo + 2, 60)


def excel(ruta: Path, hojas: dict[str, pd.DataFrame]) -> Path:
    """Un libro con una hoja por DataFrame (las vacías llevan una nota)."""
    with pd.ExcelWriter(ruta, engine="openpyxl", date_format="YYYY-MM-DD", datetime_format="YYYY-MM-DD") as xw:
        for nombre, df in hojas.items():
            if df.empty and len(df.columns) == 0:
                df = pd.DataFrame({"Nota": ["Sin estaciones"]})
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
            _ajustar_hoja(xw.sheets[nombre[:31]], df)
    return ruta


def _num(x):
    return None if x is None or pd.isna(x) else float(x)


def _fecha(x):
    return x if isinstance(x, date) else None


def shapefile_estaciones(ruta: Path, df: pd.DataFrame, lat: float, lon: float, nombre_proyecto: str) -> Path:
    """Punto del proyecto (TIPO = PROYECTO) y estaciones (TIPO = ESTACION), WGS84."""
    with shapefile.Writer(str(ruta), shapeType=shapefile.POINT, encoding="utf-8") as w:
        w.field("TIPO", "C", 10)
        w.field("CODIGO", "C", 12)
        w.field("NOMBRE", "C", 100)
        w.field("TECNOLOG", "C", 80)
        w.field("ESTADO", "C", 20)
        w.field("MUNICIPIO", "C", 60)
        w.field("LATITUD", "N", 12, 6)
        w.field("LONGITUD", "N", 12, 6)
        w.field("ELEV_MSNM", "N", 8, 1)
        w.field("DIST_KM", "N", 10, 3)
        w.field("INSTALADA", "D")
        w.field("SUSPENDIDA", "D")
        w.field("ANIOS_OPER", "N", 6, 1)
        w.field("CUMPLE", "C", 3)
        w.field("SELEC", "C", 2)
        w.field("RANGOS", "C", 200)

        w.point(lon, lat)
        w.record("PROYECTO", "", nombre_proyecto, "", "", "", lat, lon, None, 0, None, None, None, "", "", "")
        for i, r in df.iterrows():
            w.point(r["Longitud"], r["Latitud"])
            w.record(
                "ESTACION", r["Código"], r["Nombre"], r["Tecnología"], r["Estado"], r["Municipio"],
                r["Latitud"], r["Longitud"], _num(r["Elevación (msnm)"]), r["Distancia (km)"],
                _fecha(r["Instalada"]), _fecha(r["Suspendida"]), _num(r["Años de operación"]),
                r.get("Cumple", "Sí"), r.get("Seleccionada", ""), r["Rangos a descargar en DHIME"],
            )
    ruta.with_suffix(".prj").write_text(WKT_WGS84, encoding="ascii")
    ruta.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    return ruta


def series_excel_csv(series: dict[str, pd.DataFrame], carpeta: Path) -> Path:
    carpeta_csv = carpeta / "series_csv"
    carpeta_csv.mkdir(exist_ok=True)
    hojas = {}
    for codigo, serie in series.items():
        df = serie.rename(columns={"fecha": "Fecha", "precipitacion_mm": "Precipitacion_mm"})
        df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
        hojas[codigo] = df
        df.to_csv(carpeta_csv / f"{codigo}.csv", index=False, encoding="utf-8")
    return excel(carpeta / "series_precipitacion_diaria.xlsx", hojas)


def carpeta_ejecucion(base: Path, nombre_proyecto: str) -> Path:
    """salidas/Estaciones_<proyecto>; si ya existe, Estaciones_<proyecto>_2, _3, ..."""
    limpio = re.sub(r'[<>:"/\\|?*]', "", nombre_proyecto).strip().rstrip(".") or "Proyecto"
    nombre = "Estaciones_" + re.sub(r"\s+", "_", limpio)
    carpeta, i = base / nombre, 1
    while carpeta.exists():
        i += 1
        carpeta = base / f"{nombre}_{i}"
    carpeta.mkdir(parents=True)
    return carpeta
