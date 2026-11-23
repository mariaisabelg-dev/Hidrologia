# Hidrología — Caracterización hidrológica automatizada

Programa para automatizar la caracterización hidrológica de zonas de estudio en Colombia.

## Módulo 1 — Estaciones del IDEAM cercanas y precipitación diaria

Dado el punto de un proyecto (p. ej. una minigranja), escoge **las 5 estaciones del IDEAM más cercanas a menos de 50 km** que cumplen dos criterios: no se suspendieron antes de 2000 y tienen al menos 10 años de operación según el Catálogo Nacional de Estaciones. Solo consulta el catálogo, así que tarda segundos.

Las series se descargan a mano en DHIME (el IDEAM no ofrece API) y el programa las procesa. La regla es solo por distancia mientras se calibra con puntos ya estudiados; las fuentes automáticas (datos.gov.co, Piragua, Cornare) quedaron fuera por ahora porque no tienen 10 años completos de registro. Detalle en [docs/fuentes_datos.md](docs/fuentes_datos.md).

No hace cálculos hidrológicos (máximos anuales, frecuencias, etc.); eso queda para fases siguientes.

### Instalación (una vez)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### Uso

Con el lanzador: abra `buscar_estaciones.bat` con el Bloc de notas, escriba latitud, longitud y nombre en las filas indicadas, guarde y haga doble clic en el archivo. O por consola:

```powershell
.venv\Scripts\python main.py "6.2442, -75.5812" --nombre "Minigranja X"
.venv\Scripts\python main.py "6°14'39\"N 75°34'52\"W"
.venv\Scripts\python main.py          # pide las coordenadas
.venv\Scripts\python main.py --help   # todas las opciones (--radio, --n, --min-anios, --fin-minimo)
```

### Flujo con DHIME

1. Ejecute el programa con el punto. La hoja *Seleccionadas* de `resumen_estaciones.xlsx` trae las estaciones escogidas y la columna **Rangos a descargar en DHIME**. DHIME entrega máximo 29 años por descarga, así que una estación larga puede necesitar 2 o 3 archivos.
2. En [DHIME](http://dhime.ideam.gov.co/atencionciudadano/), descargue la precipitación diaria (*Día pluviométrico*) de cada rango, en CSV.
3. Deje los archivos en `datos/crudos/`, con cualquier nombre. No hace falta unirlos: el programa junta los de cada estación.
4. Ejecute de nuevo con el mismo punto. Las estaciones con archivos muestran periodo, % de faltantes y años completos, y sus series salen en `series_precipitacion_diaria.xlsx`. La columna de rangos muestra solo lo que falta.

### Entregables

Cada ejecución crea `salidas/<fecha_hora>_<lat>_<lon>/` con:

| Archivo | Contenido |
|---|---|
| `resumen_estaciones.xlsx` | Hoja *Seleccionadas* (las escogidas, con distancia, elevación, años de operación, rangos a descargar y, si ya hay archivos, periodo, % faltantes y años completos), hoja *En el radar* (todas las estaciones del IDEAM a ≤ 50 km, si cumplen y por qué no) y hoja *Criterios*. |
| `ubicacion_estaciones.shp` | Punto del proyecto (`TIPO = PROYECTO`) y estaciones escogidas, en WGS84 (EPSG:4326). |
| `estaciones_radar.shp` | Punto del proyecto y todas las estaciones del radar (campos `CUMPLE` y `SELEC`). |
| `series_precipitacion_diaria.xlsx` | Solo si hay archivos de DHIME: una hoja por estación (Fecha, Precipitacion_mm). Los días sin dato quedan vacíos. |
| `series_csv/<codigo>.csv` | Las mismas series en CSV. |

Antes de usar los datos, lea [docs/fuentes_datos.md](docs/fuentes_datos.md): explica las fuentes, sus limitaciones y los criterios aplicados.

## Estructura

| Carpeta / archivo | Contenido | ¿Se versiona en Git? |
|---|---|---|
| `main.py` | Punto de entrada por consola | Sí |
| `buscar_estaciones.bat` | Lanzador con filas para escribir latitud, longitud y nombre | Sí |
| `estaciones/` | Paquete del Módulo 1: `base.py` (contrato de fuentes), `ideam.py`, `piragua.py`, `cornare.py`, `dhime.py` (conectores; `cornare.py` no se usa por ahora), `seleccion.py` (selección por distancia y radar), `buscador.py` (motor para fuentes automáticas, sin uso por ahora), `exportar.py`, `geo.py`, `socrata.py`, `red.py` | Sí |
| `docs/` | Documentación: fuentes, metodología, decisiones, bitácora | Sí |
| `salidas/` | Entregables de cada ejecución | No (solo la carpeta) |
| `datos/` | `datos/crudos/`: CSV descargados de DHIME; insumos de otras fases (DEM, shapefiles…) | No (solo la carpeta) |
| `resultados/` | Salidas de otras fases | No (solo la carpeta) |

### Agregar una fuente nueva (CAR, SIATA…)

Crear `estaciones/<fuente>.py` con una clase que herede de `FuentePluviometrica` (ver [estaciones/base.py](estaciones/base.py)) y pasarla al buscador en `main.py`: `BuscadorEstaciones([FuenteIDEAM(), FuenteNueva()])`.

## Documentación

- [docs/fuentes_datos.md](docs/fuentes_datos.md) — fuentes, limitaciones y criterios del Módulo 1.
- [docs/bitacora.md](docs/bitacora.md) — registro cronológico de avances y decisiones.
