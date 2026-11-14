# Hidrología — Caracterización hidrológica automatizada

Programa para automatizar la caracterización hidrológica de zonas de estudio en Colombia.

## Módulo 1 — Estaciones cercanas y precipitación diaria

Dado el punto de un proyecto (p. ej. una minigranja), busca las **5 estaciones pluviométricas activas más cercanas que tienen datos** y descarga en tiempo real sus series de precipitación diaria desde los datos abiertos del IDEAM (datos.gov.co). No guarda bases de datos locales: cada ejecución consulta la fuente.

No hace cálculos hidrológicos (máximos anuales, frecuencias, etc.); eso queda para fases siguientes.

### Instalación (una vez)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### Uso

```powershell
.venv\Scripts\python main.py "6.2442, -75.5812" --nombre "Minigranja X"
.venv\Scripts\python main.py "6°14'39\"N 75°34'52\"W"
.venv\Scripts\python main.py          # pide las coordenadas
.venv\Scripts\python main.py --help   # todas las opciones
```

Una ejecución típica tarda unos minutos, la mayor parte esperando a la API.

### Entregables

Cada ejecución crea `salidas/<fecha_hora>_<lat>_<lon>/` con:

| Archivo | Contenido |
|---|---|
| `resumen_estaciones.xlsx` | Hoja *Resumen* (código, nombre, entidad, estado, ubicación, elevación, distancia, periodo de registro, total de días con dato, % faltantes), hoja *Descartadas* (candidatas más cercanas sin datos útiles y el motivo) y hoja *Criterios* (fuentes y parámetros usados). |
| `ubicacion_estaciones.shp` (+ `.shx .dbf .prj .cpg`) | Punto del proyecto (`TIPO = PROYECTO`) y estaciones (`TIPO = ESTACION`) en WGS84 (EPSG:4326), con los atributos del resumen. |
| `series_precipitacion_diaria.xlsx` | Una hoja por estación: Fecha, Precipitacion_mm. Los días sin dato válido quedan vacíos. |
| `series_csv/<codigo>.csv` | Las mismas series en CSV. |

Antes de usar los datos, lea [docs/fuentes_datos.md](docs/fuentes_datos.md): explica las fuentes, sus limitaciones (solo estaciones automáticas, duplicados, calidad) y los criterios aplicados.

## Estructura

| Carpeta / archivo | Contenido | ¿Se versiona en Git? |
|---|---|---|
| `main.py` | Punto de entrada por consola | Sí |
| `estaciones/` | Paquete del Módulo 1: `base.py` (contrato de fuentes), `ideam.py` (conector IDEAM), `buscador.py` (motor espacial), `socrata.py`, `geo.py`, `exportar.py` | Sí |
| `docs/` | Documentación: fuentes, metodología, decisiones, bitácora | Sí |
| `salidas/` | Entregables de cada ejecución | No (solo la carpeta) |
| `datos/` | Insumos locales de otras fases (DEM, shapefiles…) | No (solo la carpeta) |
| `resultados/` | Salidas de otras fases | No (solo la carpeta) |

### Agregar una fuente nueva (CAR, SIATA…)

Crear `estaciones/<fuente>.py` con una clase que herede de `FuentePluviometrica` (ver [estaciones/base.py](estaciones/base.py)) y pasarla al buscador en `main.py`: `BuscadorEstaciones([FuenteIDEAM(), FuenteNueva()])`.

## Documentación

- [docs/fuentes_datos.md](docs/fuentes_datos.md) — fuentes, limitaciones y criterios del Módulo 1.
- [docs/bitacora.md](docs/bitacora.md) — registro cronológico de avances y decisiones.
