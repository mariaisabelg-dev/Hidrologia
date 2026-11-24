"""Módulo 1 — Estaciones del IDEAM (DHIME) más cercanas y series de precipitación diaria.

Flujo:
  1. Se da el punto del proyecto. El programa lee el Catálogo Nacional de Estaciones
     y escoge las 5 estaciones del IDEAM más cercanas (≤ 50 km) que cumplen los
     criterios, con los rangos de años a descargar en DHIME. Tarda segundos.
  2. Se descargan esos rangos en DHIME y los CSV se dejan en datos/crudos/.
  3. Al ejecutar de nuevo, el programa une los archivos y entrega las series diarias
     con su periodo, % de faltantes y años completos.

Uso:
    python main.py "6.2442, -75.5812" --nombre "Minigranja X"
    python main.py "6°14'39\"N 75°34'52\"W"
    python main.py            (pide las coordenadas por consola)

Opciones: python main.py --help
"""

from __future__ import annotations

import argparse
from datetime import date
import logging
from pathlib import Path
import sys
import time

import pandas as pd

from estaciones import exportar
from estaciones.base import Estacion, anios_completos
from estaciones.buscador import estadisticas_serie
from estaciones.dhime import FuenteDHIMEArchivos
from estaciones.geo import (LON_MAX, LON_MIN, CoordenadaInvalida, leer_coordenadas, leer_valor,
                            validar_en_colombia)
from estaciones.ideam import catalogo_nacional
from estaciones.seleccion import estaciones_en_radar

RAIZ = Path(__file__).resolve().parent


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Escoge las estaciones del IDEAM (DHIME) más cercanas a un punto y "
                                "procesa los CSV de DHIME que se hayan descargado.")
    p.add_argument("coordenadas", nargs="*", help="Latitud y longitud (decimal o GMS). Ej: \"6.2442, -75.5812\"")
    p.add_argument("--nombre", default="Proyecto", help="Nombre del proyecto/minigranja (va al shapefile).")
    p.add_argument("--n", type=int, default=5, help="Máximo de estaciones a escoger (defecto 5).")
    p.add_argument("--radio", type=float, default=50, help="Radio de búsqueda en km (defecto 50).")
    p.add_argument("--min-anios", type=int, default=10,
                   help="Años mínimos de operación según el catálogo (defecto 10).")
    p.add_argument("--fin-minimo", type=int, default=2000,
                   help="Descarta estaciones suspendidas antes de este año (defecto 2000).")
    p.add_argument("--cobertura-anual", type=float, default=0.8,
                   help="Fracción mínima de días con dato para que un año cuente como completo (defecto 0.8).")
    p.add_argument("--dhime", type=Path, default=RAIZ / "datos" / "crudos",
                   help="Carpeta con los CSV descargados de DHIME (defecto datos/crudos).")
    p.add_argument("--salidas", type=Path, default=RAIZ / "salidas", help="Carpeta base de entregables.")
    p.add_argument("-v", "--verbose", action="store_true", help="Muestra más detalle del proceso.")
    return p.parse_args()


def pedir_coordenadas(texto: str | None) -> tuple[float, float]:
    """Usa las coordenadas de la línea de comandos o, si no hay, las pide por consola."""
    if texto is not None:
        try:
            return leer_coordenadas(texto)
        except CoordenadaInvalida as e:
            raise SystemExit(f"Error: {e}")

    print("Ingrese las coordenadas del proyecto (WGS84).")
    print("  Acepta decimales (6.2442 / -75.5812) o grados-minutos-segundos (6 14 39 N / 75 34 52 W).")
    while True:
        try:
            lat = leer_valor(input("  Latitud : ").strip(), "lat")
            lon = leer_valor(input("  Longitud: ").strip(), "lon")
            if lon > 0 and LON_MIN <= -lon <= LON_MAX:
                lon = -lon
                print(f"  (Longitud tomada como Oeste: {lon})")
            validar_en_colombia(lat, lon)
            return lat, lon
        except CoordenadaInvalida as e:
            print(f"  {e}\n  Intente de nuevo.")


def procesar_cargadas(sel: pd.DataFrame, dhime: FuenteDHIMEArchivos, cobertura_anual: float):
    """Series diarias de las estaciones escogidas que ya tienen CSV de DHIME."""
    series, stats = {}, []
    for _, r in sel.iterrows():
        if r["Código"] not in dhime.periodos:
            stats.append({})
            continue
        e = Estacion(r["Código"], r["Nombre"], dhime.nombre, "IDEAM", "", "", "", "", "", 0.0, 0.0)
        crudo = dhime.serie_diaria(e, date(1900, 1, 1), date.today())
        serie = crudo[["fecha", "precipitacion_mm"]]
        dias = pd.date_range(serie["fecha"].min(), serie["fecha"].max(), freq="D")
        serie = serie.set_index("fecha").reindex(dias).rename_axis("fecha").reset_index()
        series[r["Código"]] = serie
        est = estadisticas_serie(serie)
        stats.append({
            "Fecha inicio": est["fecha_inicio"],
            "Fecha fin": est["fecha_fin"],
            "Total registros (días)": est["total_registros"],
            "% faltantes": est["pct_faltantes"],
            "Años completos": anios_completos(serie, cobertura_anual),
        })
    stats = pd.DataFrame(stats, index=sel.index)
    if "Años completos" in stats:
        stats["Años completos"] = stats["Años completos"].astype("Int64")
    return series, stats


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = argumentos()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    lat, lon = pedir_coordenadas(" ".join(args.coordenadas) if args.coordenadas else None)
    if not args.coordenadas and args.nombre == "Proyecto":
        args.nombre = input("  Nombre del proyecto (Enter para omitir): ").strip() or "Proyecto"
    print(f"\nPunto del proyecto: lat {lat:.6f}, lon {lon:.6f}  (WGS84)\n")
    t0 = time.time()

    logging.info("Leyendo el Catálogo Nacional de Estaciones (IDEAM)...")
    nacional = catalogo_nacional()
    dhime = FuenteDHIMEArchivos(args.dhime, nacional)
    fin_minimo = date(args.fin_minimo, 1, 1)
    radar = estaciones_en_radar(lat, lon, nacional, dhime.periodos, n=args.n, radio_km=args.radio,
                                fin_minimo=fin_minimo, min_anios=args.min_anios)
    sel = radar[radar["Seleccionada"] != ""].copy() if not radar.empty else pd.DataFrame()
    series = {}
    if not sel.empty:
        series, stats = procesar_cargadas(sel, dhime, args.cobertura_anual)
        sel = pd.concat([sel.drop(columns=["Cumple", "Motivo"]), stats], axis=1)

    carpeta = exportar.carpeta_ejecucion(args.salidas, args.nombre)
    criterios = {
        "Proyecto": args.nombre,
        "Latitud proyecto": lat,
        "Longitud proyecto": lon,
        "Fecha de consulta": date.today().isoformat(),
        "Fuente": "Catálogo Nacional de Estaciones del IDEAM (datos.gov.co hp9r-jxuu); series de DHIME "
        f"descargadas a mano en {args.dhime} ({len(dhime.periodos)} estaciones cargadas)",
        "Estaciones consideradas": "entidad IDEAM, categorías que miden precipitación, cualquier tecnología",
        "Radio de búsqueda": f"{args.radio:g} km (Haversine, esfera de radio 6371.0088 km)",
        "Estación cumple si": f"no está suspendida antes de {fin_minimo} y tiene ≥ {args.min_anios} años de "
        "operación entre su instalación y hoy (o su suspensión), según el catálogo",
        "Selección": f"las {args.n} más cercanas que cumplen (regla por distancia, en calibración)",
        "Rangos a descargar en DHIME": "periodo de operación partido en tramos de máximo 29 años "
        "(límite del portal), descontando lo ya cargado",
        "Día pluviométrico": "el de DHIME: lectura a las 7:00 en convencionales",
        "Año completo si": f"≥ {args.cobertura_anual:.0%} de sus días con dato",
        "% faltantes": "días sin dato entre Fecha inicio y Fecha fin de lo cargado",
    }
    meta = pd.DataFrame({"Parámetro": list(criterios), "Valor": [str(v) for v in criterios.values()]})
    exportar.excel(carpeta / "resumen_estaciones.xlsx",
                   {"Seleccionadas": sel, "En el radar": radar, "Criterios": meta})
    exportar.shapefile_estaciones(carpeta / "ubicacion_estaciones.shp", sel, lat, lon, args.nombre)
    exportar.shapefile_estaciones(carpeta / "estaciones_radar.shp", radar, lat, lon, args.nombre)
    if series:
        exportar.series_excel_csv(series, carpeta)

    with pd.option_context("display.width", 250, "display.max_columns", None, "display.max_colwidth", 45):
        if radar.empty:
            print(f"No hay estaciones del IDEAM a menos de {args.radio:g} km.")
        else:
            cumplen = (radar["Cumple"] == "Sí").sum()
            print(f"EN EL RADAR: {len(radar)} estaciones del IDEAM a ≤ {args.radio:g} km; {cumplen} cumplen los criterios.")
        if sel.empty:
            print("Ninguna cumple los criterios: ver la hoja 'En el radar'.")
        else:
            print(f"\nESCOGIDAS ({len(sel)})")
            cols = ["Código", "Nombre", "Tecnología", "Estado", "Distancia (km)", "Elevación (msnm)",
                    "Años de operación", "Rangos a descargar en DHIME"]
            print(sel[cols].to_string(index=False))
            if series:
                print("\nCON ARCHIVOS DE DHIME CARGADOS")
                cols = ["Código", "Nombre", "Fecha inicio", "Fecha fin", "% faltantes", "Años completos"]
                print(sel[sel["Código"].isin(series)][cols].to_string(index=False))
    print(f"\nEntregables en: {carpeta}\nTiempo total: {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
