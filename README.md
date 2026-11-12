# Hidrología — Caracterización hidrológica automatizada

Programa para automatizar la caracterización hidrológica de zonas de estudio.

> Estado: en definición. El alcance, los datos de entrada y la metodología se documentarán en `docs/`.

## Estructura

| Carpeta | Contenido | ¿Se versiona en Git? |
|---|---|---|
| `src/` | Código fuente del programa | Sí |
| `docs/` | Documentación: alcance, metodología, decisiones, bitácora | Sí |
| `datos/crudos/` | Datos de entrada originales (DEM, shapefiles, series de caudal/precipitación…) | No (solo la carpeta) |
| `datos/procesados/` | Datos intermedios generados por el programa | No (solo la carpeta) |
| `resultados/` | Salidas finales (tablas, figuras, reportes) | No (solo la carpeta) |

Los datos y resultados no se suben a Git porque suelen ser pesados y se pueden regenerar. Se debe documentar en `docs/` de dónde se obtiene cada dato.

## Documentación

- [docs/bitacora.md](docs/bitacora.md) — registro cronológico de avances y decisiones.
