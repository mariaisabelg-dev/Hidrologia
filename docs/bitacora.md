# Bitácora del proyecto

Registro cronológico de avances, decisiones y pendientes. La entrada más reciente va arriba.

## 2026-11-14 — Módulo 1: estaciones cercanas y precipitación diaria

- Se crea el paquete `estaciones/` (contrato `FuentePluviometrica`, conector IDEAM, buscador espacial, exportadores) y `main.py`. Ver [fuentes_datos.md](fuentes_datos.md).
- Entrada de coordenadas por consola (latitud y longitud por separado, decimal o GMS) o como argumento; lanzador `buscar_estaciones.bat`.
- Fuentes: catálogo CNE `hp9r-jxuu` y precipitación `s54a-sgyg` (solo estaciones automáticas; las convencionales no tienen API abierta).
- Hallazgos: `s54a-sgyg` trae cada observación duplicada (se deduplica antes de sumar); `ORDER BY` en la API es impredecible, por lo que la verificación y la descarga usan consultas acotadas por fecha; en el Valle de Aburrá las estaciones SIATA/AMVA figuran en el catálogo pero no publican datos.
- Prueba en Medellín (6.2442, -75.5812): 5 estaciones confirmadas (Olaya Herrera 2,3 km; Santa Elena 8,8 km; Metromedellín 10,0 km; Aeropuerto JMC 19,1 km; La Selva 22,3 km) en ~6 min. Metromedellín tiene 55 % de faltantes y promedio bajo (0,9 mm/día): revisar.
- Pendiente: decidir día pluviométrico 00–24 h vs 07–07 h; conectores SIATA/CAR/DHIME para series largas.

## 2026-11-12 — Creación del repositorio

- Se crea la carpeta `Hidrologia` y se inicia el repositorio Git (rama `main`).
- Estructura inicial: `src/`, `docs/`, `datos/crudos/`, `datos/procesados/`, `resultados/`.
- Se conecta el repositorio remoto en GitHub: https://github.com/mariaisabelg-dev/Hidrologia (respaldo en línea).
- Pendiente: definir alcance, datos de entrada y metodología de la caracterización.
