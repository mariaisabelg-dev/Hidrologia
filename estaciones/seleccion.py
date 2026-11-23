"""Selección de estaciones del IDEAM (DHIME) cercanas a un punto.

Solo usa el Catálogo Nacional de Estaciones (datos.gov.co hp9r-jxuu): no descarga
series, así que responde en segundos. Las series se descargan a mano en DHIME y se
dejan en datos/crudos/ (ver estaciones/dhime.py).

Regla actual (2026-11-19): las `n` estaciones más cercanas dentro de `radio_km` que
cumplen los criterios de vigencia y longitud según las fechas del catálogo. Es una
regla por distancia, para calibrar contra puntos ya estudiados antes de definir
reglas más finas.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .geo import haversine_km

MAX_ANIOS_DHIME = 29  # el portal entrega máximo 29 años por descarga


def rangos_dhime(inicio: date | None, fin: date, cargado: tuple[date, date] | None) -> list[tuple[date, date]]:
    """Tramos de ≤ 29 años que faltan por descargar entre `inicio` y `fin`."""
    if inicio is None:
        return []
    faltan: list[tuple[int, int]] = []
    if cargado is None:
        faltan.append((inicio.year, fin.year))
    else:
        c0, c1 = cargado
        if c0.year - inicio.year > 1:  # el primer año de registro suele estar incompleto
            faltan.append((inicio.year, c0.year - 1))
        if c1.year < fin.year:
            faltan.append((c1.year + 1, fin.year))
    tramos = []
    for a, b in faltan:
        while a <= b:
            z = min(a + MAX_ANIOS_DHIME - 1, b)
            tramos.append((date(a, 1, 1), min(date(z, 12, 31), fin)))
            a = z + 1
    return tramos


def estaciones_en_radar(
    lat: float,
    lon: float,
    catalogo_nacional: list[dict],
    cargadas: dict[str, tuple[date, date, int]] | None = None,
    n: int = 5,
    radio_km: float = 50,
    fin_minimo: date = date(2000, 1, 1),
    min_anios: int = 10,
) -> pd.DataFrame:
    """Todas las estaciones del IDEAM que miden precipitación dentro de `radio_km`,
    ordenadas por distancia, con columnas "Cumple", "Motivo" y "Seleccionada"
    (las `n` más cercanas que cumplen)."""
    cargadas = cargadas or {}
    hoy = date.today()
    filas = []
    for f in catalogo_nacional:
        if f["entidad"] != "IDEAM":
            continue
        dist = haversine_km(lat, lon, f["latitud"], f["longitud"])
        if dist > radio_km:
            continue
        suspendida = f["estado"] == "Suspendida"
        fin = (f["suspension"] or hoy) if suspendida else hoy
        anios = round((fin - f["instalacion"]).days / 365.25, 1) if f["instalacion"] else None
        motivos = []
        if suspendida and (f["suspension"] is None or f["suspension"] < fin_minimo):
            motivos.append(f"suspendida antes de {fin_minimo.year}" if f["suspension"] else "suspendida, sin fecha")
        if anios is None:
            motivos.append("sin fecha de instalación en el catálogo")
        elif anios < min_anios:
            motivos.append(f"{anios} años de operación (< {min_anios})")
        carg = cargadas.get(f["codigo"])
        rangos = rangos_dhime(f["instalacion"], fin, carg[:2] if carg else None)
        filas.append(
            {
                "Código": f["codigo"],
                "Nombre": f["nombre"],
                "Categoría": f["categoria"],
                "Tecnología": f["tecnologia"],
                "Estado": f["estado"],
                "Departamento": f["departamento"],
                "Municipio": f["municipio"],
                "Latitud": f["latitud"],
                "Longitud": f["longitud"],
                "Elevación (msnm)": f["altitud"],
                "Distancia (km)": round(dist, 2),
                "Instalada": f["instalacion"],
                "Suspendida": f["suspension"] if suspendida else None,
                "Años de operación": anios,
                "Cumple": "No" if motivos else "Sí",
                "Motivo": "; ".join(motivos),
                "Ya cargado (DHIME)": f"{carg[0]} a {carg[1]} ({carg[2]} archivo(s))" if carg else "",
                "Rangos a descargar en DHIME": "; ".join(f"{a} a {b}" for a, b in rangos) or "completo",
            }
        )
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas).sort_values("Distancia (km)").reset_index(drop=True)
    elegidas = df.index[df["Cumple"] == "Sí"][:n]
    df["Seleccionada"] = ""
    df.loc[elegidas, "Seleccionada"] = [str(i + 1) for i in range(len(elegidas))]
    return df
