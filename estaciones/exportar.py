"""Escritura de entregables: resumen (Excel), shapefile y series (Excel + CSV)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import shapefile  # pyshp

from .buscador import ResultadoBusqueda

WKT_WGS84 = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def _ajustar_hoja(ws, df: pd.DataFrame) -> None:
    ws.freeze_panes = "A2"
    for i, col in enumerate(df.columns, start=1):
        largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(500)])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(largo + 2, 60)


def _escribir_excel(ruta: Path, hojas: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(ruta, engine="openpyxl", date_format="YYYY-MM-DD", datetime_format="YYYY-MM-DD") as xw:
        for nombre, df in hojas.items():
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
            _ajustar_hoja(xw.sheets[nombre[:31]], df)


def resumen_excel(res: ResultadoBusqueda, carpeta: Path, criterios: dict) -> Path:
    descartadas = pd.DataFrame(
        [
            {"Código": e.codigo, "Nombre": e.nombre, "Distancia (km)": e.distancia_km, "Motivo": motivo}
            for e, motivo in res.descartadas
        ]
    )
    meta = pd.DataFrame({"Parámetro": list(criterios), "Valor": [str(v) for v in criterios.values()]})
    ruta = carpeta / "resumen_estaciones.xlsx"
    _escribir_excel(ruta, {"Resumen": res.resumen, "Descartadas": descartadas, "Criterios": meta})
    return ruta


def series_excel_csv(res: ResultadoBusqueda, carpeta: Path) -> Path:
    carpeta_csv = carpeta / "series_csv"
    carpeta_csv.mkdir(exist_ok=True)
    hojas = {}
    for codigo, serie in res.series.items():
        df = serie.rename(columns={"fecha": "Fecha", "precipitacion_mm": "Precipitacion_mm"})
        df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
        hojas[codigo] = df
        df.to_csv(carpeta_csv / f"{codigo}.csv", index=False, encoding="utf-8")
    ruta = carpeta / "series_precipitacion_diaria.xlsx"
    _escribir_excel(ruta, hojas)
    return ruta


def shapefile_ubicacion(res: ResultadoBusqueda, carpeta: Path, nombre_proyecto: str) -> Path:
    ruta = carpeta / "ubicacion_estaciones.shp"
    with shapefile.Writer(str(ruta), shapeType=shapefile.POINT, encoding="utf-8") as w:
        w.field("TIPO", "C", 10)
        w.field("CODIGO", "C", 12)
        w.field("NOMBRE", "C", 100)
        w.field("ENTIDAD", "C", 100)
        w.field("FUENTE", "C", 20)
        w.field("ESTADO", "C", 20)
        w.field("DEPTO", "C", 50)
        w.field("MUNICIPIO", "C", 60)
        w.field("LATITUD", "N", 12, 6)
        w.field("LONGITUD", "N", 12, 6)
        w.field("ELEV_MSNM", "N", 8, 1)
        w.field("DIST_KM", "N", 10, 3)
        w.field("F_INICIO", "D")
        w.field("F_FIN", "D")
        w.field("N_REGIST", "N", 8, 0)
        w.field("PCT_FALT", "N", 6, 2)

        w.point(res.longitud, res.latitud)
        w.record("PROYECTO", "", nombre_proyecto, "", "", "", "", "",
                 res.latitud, res.longitud, None, 0, None, None, None, None)

        for _, r in res.resumen.iterrows():
            w.point(r["Longitud"], r["Latitud"])
            w.record(
                "ESTACION", r["Código"], r["Nombre"], r["Entidad"], r["Fuente"], r["Estado"],
                r["Departamento"], r["Municipio"], r["Latitud"], r["Longitud"],
                None if pd.isna(r["Elevación (msnm)"]) else r["Elevación (msnm)"],
                r["Distancia (km)"], r["Fecha inicio"], r["Fecha fin"],
                r["Total registros (días)"], r["% faltantes"],
            )
    ruta.with_suffix(".prj").write_text(WKT_WGS84, encoding="ascii")
    ruta.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    return ruta


def carpeta_ejecucion(base: Path, lat: float, lon: float) -> Path:
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = base / f"{marca}_{lat:.4f}_{lon:.4f}"
    carpeta.mkdir(parents=True, exist_ok=False)
    return carpeta
