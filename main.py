"""Módulo 1 — Estaciones pluviométricas más cercanas y series de precipitación diaria.

Uso:
    python main.py "6.2442, -75.5812"
    python main.py "6°14'39\"N 75°34'52\"W" --nombre "Minigranja X"
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

from estaciones import BuscadorEstaciones, FuenteIDEAM
from estaciones import exportar
from estaciones.cornare import FuenteCornare
from estaciones.manual import estaciones_para_descarga_manual
from estaciones.piragua import FuentePiragua
from estaciones.geo import (LON_MAX, LON_MIN, CoordenadaInvalida, leer_coordenadas, leer_valor,
                            validar_en_colombia)

RAIZ = Path(__file__).resolve().parent


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Busca las estaciones pluviométricas activas más cercanas a un punto "
                                "y descarga sus series de precipitación diaria (IDEAM, datos.gov.co).")
    p.add_argument("coordenadas", nargs="*", help="Latitud y longitud (decimal o GMS). Ej: \"6.2442, -75.5812\"")
    p.add_argument("--nombre", default="Proyecto", help="Nombre del proyecto/minigranja (va al shapefile).")
    p.add_argument("--n", type=int, default=5, help="Número de estaciones a seleccionar (defecto 5).")
    p.add_argument("--desde", type=int, default=2003, help="Año inicial de descarga (defecto 2003, inicio del dataset).")
    p.add_argument("--max-dias-sin-datos", type=int, default=365,
                   help="Descarta estaciones cuyo último dato sea más antiguo que esto (defecto 365).")
    p.add_argument("--cobertura-minima", type=float, default=0.8,
                   help="Fracción mínima de registros de 10 min para validar un día (defecto 0.8).")
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

    ideam = FuenteIDEAM(cobertura_minima=args.cobertura_minima)
    fuentes = [
        ideam,
        FuentePiragua(cobertura_minima=args.cobertura_minima),
        FuenteCornare(cobertura_minima=args.cobertura_minima),
    ]
    buscador = BuscadorEstaciones(fuentes)
    res = buscador.buscar(lat, lon, n=args.n, max_dias_sin_datos=args.max_dias_sin_datos)
    if not res.estaciones:
        raise SystemExit("No se encontró ninguna estación con datos disponibles.")
    buscador.descargar_series(res, desde=date(args.desde, 1, 1))

    logging.info("Buscando estaciones cercanas para descarga manual...")
    manual = estaciones_para_descarga_manual(lat, lon, excluir={e.codigo for e in res.estaciones})

    carpeta = exportar.carpeta_ejecucion(args.salidas, lat, lon)
    criterios = {
        "Proyecto": args.nombre,
        "Latitud proyecto": lat,
        "Longitud proyecto": lon,
        "Fecha de consulta": date.today().isoformat(),
        "Fuentes automáticas": "IDEAM y terceros (datos.gov.co hp9r-jxuu, 57sv-p2fu, s54a-sgyg); "
        "Piragua-Corantioquia (piragua.corantioquia.gov.co); MARCO-Cornare (marco.cornare.gov.co)",
        "Fuentes no disponibles en esta ejecución": ", ".join(buscador.fuentes_caidas) or "ninguna",
        "Filtro catálogo IDEAM": "estado = Activa, tecnología automática, categoría con medición de precipitación",
        "Descarga manual": "10 estaciones IDEAM (DHIME) + 10 de otras entidades, activas, ≤ 50 km, del catálogo nacional y SIATA, "
        "que no están entre las seleccionadas",
        "Estación confirmada si": f"tiene datos y el último es de hace ≤ {args.max_dias_sin_datos} días",
        "Distancia": "Haversine (esfera de radio 6371.0088 km)",
        "Día pluviométrico": "día calendario 00:00–24:00 hora local (suma de registros de 10 min, deduplicados)",
        "Día válido si": f"tiene ≥ {args.cobertura_minima:.0%} de los registros esperados ese día",
        "% faltantes": "días sin dato válido entre Fecha inicio y Fecha fin",
        "Descarga desde": f"{args.desde}-01-01",
        "Bloques no descargados": "; ".join(f"{c} {a}–{b}" for c, a, b in ideam.bloques_fallidos) or "ninguno",
    }
    exportar.resumen_excel(res, carpeta, criterios, manual)
    exportar.shapefile_ubicacion(res, carpeta, args.nombre)
    exportar.shapefile_manual(manual, carpeta)
    exportar.series_excel_csv(res, carpeta)

    columnas = ["Código", "Nombre", "Entidad", "Fuente", "Municipio", "Elevación (msnm)", "Distancia (km)",
                "Fecha inicio", "Fecha fin", "Total registros (días)", "% faltantes"]
    with pd.option_context("display.width", 220, "display.max_columns", None, "display.max_colwidth", 40):
        print("\nESTACIONES SELECCIONADAS (descarga automática)")
        print(res.resumen[columnas].to_string(index=False))
        if not manual.empty:
            print(f"\nPARA DESCARGA MANUAL: {len(manual)} estaciones cercanas sin descarga automática "
                  "(hoja 'Descarga manual' y estaciones_descarga_manual.shp)")
            print(manual[["Código", "Nombre", "Entidad", "Tecnología", "Distancia (km)"]].head(8).to_string(index=False))
    if res.descartadas:
        print(f"\nCandidatas descartadas por no tener datos útiles: {len(res.descartadas)} (ver hoja 'Descartadas').")
    if ideam.bloques_fallidos:
        print(f"ATENCIÓN: {len(ideam.bloques_fallidos)} bloques de datos no se pudieron descargar (ver hoja 'Criterios').")
    print(f"\nEntregables en: {carpeta}\nTiempo total: {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
