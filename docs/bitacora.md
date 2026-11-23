# Bitácora del proyecto

Registro cronológico de avances, decisiones y pendientes. La entrada más reciente va arriba.

## 2026-11-23 — Solo estaciones DHIME, selección por distancia

- Prueba de Medellín con el criterio de 10 años completos sobre fuentes automáticas: 0 estaciones cumplieron (la mejor, 8 años); tomó ~18 h y falló al exportar sin series. Conclusión: las series largas están en DHIME.
- Decisión del usuario: usar solo estaciones del IDEAM (DHIME), máximo 5, las más cercanas a ≤ 50 km. Calibrar con puntos ya estudiados antes de definir reglas más finas.
- Nuevo flujo: `seleccion.py` escoge con el catálogo (segundos) y entrega rangos de ≤ 29 años a descargar; hoja *En el radar* con todas las estaciones del radio. Los CSV de DHIME en `datos/crudos/` se unen y se reportan periodo, % faltantes y años completos.
- Pruebas: Abejorral 16 s (la estación 26180160 con su archivo 1971–1999: 27 años completos); Medellín 5 s (Laureles, Olaya Herrera convencional y automática, Villanueva, Pajarito).

## 2026-11-14 (noche) — Criterios de selección y flujo DHIME

- Criterios definidos por el usuario: la estación sirve si tiene al menos 10 años de registro y no se suspendió antes de 2000. Implementado como: dato posterior a 2000-01-01, y ≥ 10 años completos (años con ≥ 80 % de días con dato). Se descarga toda la historia disponible en cada fuente.
- Lector de CSV de DHIME (`estaciones/dhime.py`): une varios archivos por estación, porque DHIME limita cada descarga a 29 años. La hoja *Descarga manual* ahora incluye estaciones suspendidas después de 2000, años de operación, lo ya cargado y los tramos de ≤ 29 años que faltan.
- Cornare (MARCO) sale de la selección automática: solo tiene datos desde 2025.
- Aclarado: las estaciones de otras entidades que transmiten por el IDEAM (IDIGER, ISAGEN, FOPAE…) siguen incluidas; su historia está en `s54a-sgyg`. Las que se descartan en el Valle de Aburrá (AMVA/SIATA) son las que no publican datos.
- Cartas de solicitud de acceso a datos para IDEAM, SIATA, EPM, CAR y Cornare (documento aparte).

## 2026-11-14 (tarde) — Más fuentes de datos

- Inventario de fuentes abiertas de precipitación en Colombia (Antioquia, otras regiones y fuentes globales); resultado en [fuentes_datos.md](fuentes_datos.md).
- Integradas: estaciones de terceros que transmiten por el IDEAM (`57sv-p2fu`), Piragua (Corantioquia, 107 estaciones, diaria desde 2013) y MARCO (Cornare, 32 estaciones, desde 2025).
- Nueva hoja *Descarga manual* + shapefile: 10 estaciones IDEAM (DHIME, incluidas convencionales de series largas) y 10 de otras entidades (SIATA, AMVA, CAR…) más cercanas.
- Correcciones: códigos IDEAM con/sin ceros iniciales; en Piragua los días vacíos llegan como 0 mm con 0 % de datos (ahora se exige cobertura también al verificar); certificados SSL incompletos de Cornare resueltos con `truststore`.
- Prueba Medellín: 3 estaciones Piragua + 2 IDEAM en ~2–6 min.
- Pendiente: lector de archivos descargados manualmente de DHIME (falta archivo de ejemplo); definir si la selección debe priorizar calidad (% faltantes, longitud) además de distancia.

## 2026-11-14 — Módulo 1: estaciones cercanas y precipitación diaria

- Se crea el paquete `estaciones/` (contrato `FuentePluviometrica`, conector IDEAM, buscador espacial, exportadores) y `main.py`. Ver [fuentes_datos.md](fuentes_datos.md).
- Entrada de coordenadas por consola (latitud y longitud por separado, decimal o GMS) o como argumento; lanzador `buscar_estaciones.bat`.
- Fuentes: catálogo CNE `hp9r-jxuu` y precipitación `s54a-sgyg` (solo estaciones automáticas; las convencionales no tienen API abierta).
- Hallazgos: `s54a-sgyg` trae cada observación duplicada (se deduplica antes de sumar); `ORDER BY` en la API es impredecible, por lo que la verificación y la descarga usan consultas acotadas por fecha; en el Valle de Aburrá las estaciones SIATA/AMVA figuran en el catálogo pero no publican datos.
- Prueba en Medellín (6.2442, -75.5812): 5 estaciones confirmadas (Olaya Herrera 2,3 km; Santa Elena 8,8 km; Metromedellín 10,0 km; Aeropuerto JMC 19,1 km; La Selva 22,3 km) en ~6 min. Metromedellín tiene 55 % de faltantes y promedio bajo (0,9 mm/día): revisar.
- Decidido: día de lluvia 00:00–24:00.
- `buscar_estaciones.bat` con filas editables de Latitud, Longitud y Nombre del proyecto.
- DHIME revisado: sin API pública; no se automatiza su servicio interno (ver fuentes_datos.md). Pendiente decidir: lectura de descargas manuales de DHIME y/o solicitud formal al IDEAM.

## 2026-11-12 — Creación del repositorio

- Se crea la carpeta `Hidrologia` y se inicia el repositorio Git (rama `main`).
- Estructura inicial: `src/`, `docs/`, `datos/crudos/`, `datos/procesados/`, `resultados/`.
- Se conecta el repositorio remoto en GitHub: https://github.com/mariaisabelg-dev/Hidrologia (respaldo en línea).
- Pendiente: definir alcance, datos de entrada y metodología de la caracterización.
