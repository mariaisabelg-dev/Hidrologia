# Fuentes de datos y criterios — Módulo 1 (estaciones y precipitación diaria)

Verificado contra la API el 2026-11-13.

## Fuentes

| Uso | Dataset en datos.gov.co | Contenido |
|---|---|---|
| Catálogo de estaciones | [`hp9r-jxuu`](https://www.datos.gov.co/resource/hp9r-jxuu.json) — Catálogo Nacional de Estaciones (CNE) del IDEAM | Código, nombre, categoría, tecnología, estado, ubicación, altitud y entidad de ~19.000 estaciones del país (IDEAM y otras entidades). |
| Precipitación | [`s54a-sgyg`](https://www.datos.gov.co/resource/s54a-sgyg.json) — Precipitación (IDEAM) | Observaciones cada 10 min (algunas estaciones cada 1 min) de las estaciones **automáticas** del IDEAM, desde ~2003, actualizadas varias veces al día. Más de 165 millones de filas. |

Los datasets `ksew-j3zj`, `m84s-22dd`, `uwim-sqxg` y `ns63-ha4g` son vistas de `s54a-sgyg`, no fuentes nuevas.

## Limitaciones importantes

1. **Solo estaciones automáticas.** Las estaciones convencionales (pluviómetro de lectura diaria, la mayoría de la red histórica) no publican series en datos.gov.co. Sus datos están en [DHIME](http://dhime.ideam.gov.co/atencionciudadano/), que no tiene API abierta. Por eso el módulo filtra el catálogo por tecnología automática. Consecuencia: las series descargadas empiezan como muy pronto en 2003 y en muchas estaciones solo desde ~2017. Para análisis de frecuencias de largo plazo habrá que complementar con DHIME o con las CAR.
2. **Estaciones que están en el catálogo pero no publican datos.** El catálogo incluye estaciones de otras redes (p. ej. SIATA/AMVA en el Valle de Aburrá) marcadas como activas y automáticas, pero sus datos no están en `s54a-sgyg`. El buscador las descarta y las lista en la hoja *Descartadas*. Es la razón para tener conectores por CAR/red en fases siguientes.
3. **Registros duplicados.** `s54a-sgyg` trae cada observación dos veces. Antes de sumar se agrupa por fecha de observación (`max` por instante), en el servidor.
4. **Calidad.** El IDEAM indica que se aplicó un control de calidad básico (OMM). Aun así se observaron series dudosas (p. ej. lluvia diaria constante en temporada seca en el aeropuerto de El Banco). Las series se entregan sin corrección: revisarlas antes de usarlas.
5. **Rendimiento de la API.** Agregar toda la historia de una estación en una sola consulta supera el límite de tiempo del servidor; `ORDER BY` sobre este dataset es impredecible (de 4 s a más de 150 s). Por eso:
   - la verificación primero comprueba que la estación exista y luego busca su último dato en ventanas cortas;
   - la descarga va en bloques de 6 meses, en paralelo, y un bloque que se demora se parte en dos.
   Si un bloque falla definitivamente, queda registrado en la hoja *Criterios* del resumen.

## Criterios del procesamiento

| Paso | Criterio |
|---|---|
| Candidatas | Catálogo con `estado = Activa`, tecnología automática y categoría que mide precipitación (pluviométrica, pluviográfica, climatológicas, agrometeorológica, sinópticas, meteorológica especial, hidrometeorológica). Filas repetidas del catálogo: una por código. Coordenadas: campos `latitud`/`longitud` (el campo `ubicaci_n` las trae invertidas). |
| Distancia | Haversine, radio medio terrestre 6371.0088 km. |
| Confirmación | Por orden de distancia: la estación debe tener datos de precipitación y el último debe ser de hace ≤ 365 días (`--max-dias-sin-datos`). Se toman las 5 primeras confirmadas (`--n`). |
| Día pluviométrico | Día calendario 00:00–24:00 en la hora de la fuente (hora local). Decisión confirmada el 2026-11-14 (no se usa el día convencional 07:00–07:00). |
| Día válido | Debe tener ≥ 80 % de las observaciones esperadas (`--cobertura-minima`). Las esperadas por día son la moda del número de observaciones diarias en ese año, para adaptarse a estaciones de 10 min o de 1 min. Los días incompletos quedan vacíos. |
| % faltantes | Días sin dato válido entre la primera y la última fecha con dato, sobre el total de días de ese periodo. |

## DHIME (revisado 2026-11-14)

- `dhime.ideam.gov.co/atencionciudadano/` ahora redirige a `atencionciudadano.ideam.gov.co`: una aplicación web de ArcGIS para consultar y descargar manualmente las series (incluidas las estaciones convencionales).
- No tiene API pública documentada. La aplicación usa por debajo un servicio interno (`modulopersonalizado.ideam.gov.co/DhimeServicePortal`) autenticado con una cuenta de servicio propia del portal. Además, aplica límites de estaciones y fechas por descarga, y la página de entrada tiene un control anti-bots.
- **Decisión:** no automatizar ese servicio interno. Usar credenciales que el IDEAM no nos entregó y saltarse sus límites no es un acceso autorizado, y puede dejar de funcionar sin aviso.
- El portal no tiene cuentas de usuario (no hay inicio de sesión personal) ni texto de términos de uso publicado.
- Prueba 2026-11-14: al abrir el portal con un navegador automatizado (Playwright/Chromium), el firewall del IDEAM respondió "Web Page Blocked" (Attack ID 20000051), es decir, bloquea activamente el acceso automatizado. No se intentó evadir el bloqueo: hacerlo iría contra un control explícito del IDEAM y podría hacer que bloqueen la IP de la empresa.
- Alternativas viables: (a) descargar manualmente desde el portal y que el programa lea esos archivos; (b) solicitar formalmente al IDEAM acceso a un servicio o entrega de datos.

## Inventario de fuentes (revisado 2026-11-14)

Cada fuente se probó con peticiones reales. "Automática" = integrada en el programa.

### Integradas (descarga automática)

| Fuente | Módulo | Estaciones con lluvia | Resolución / historia | Actualidad | Notas |
|---|---|---|---|---|---|
| IDEAM — datos.gov.co `s54a-sgyg` + catálogo `hp9r-jxuu` | `ideam.py` | ~1.900 automáticas en catálogo (solo una parte publica datos) | 10 min (algunas 1 min), desde 2003 | ~1 día | Duplicados, ver arriba. |
| Terceros que transmiten por el IDEAM — `57sv-p2fu` (IDIGER, FOPAE, ISAGEN, PNN, CAS, EAAB, CVC, CRQ) | `ideam.py` | ~89 | Igual que `s54a-sgyg` cuando están allí | Variable: IDIGER llega hasta 2026-07, ISAGEN hasta 2017 | `57sv-p2fu` solo guarda las últimas ~12 h; se usa para descubrir estaciones. El filtro de 365 días descarta las desactualizadas. |
| Piragua — Corantioquia (`piragua.corantioquia.gov.co/api/v1`) | `piragua.py` | 85 pluviógrafos + 22 meteorológicas | Diaria (también horaria y 5–10 min), desde 2013 | ~1 día | Trae `porc_datos` (% del día). El campo `calidad` (1, 2, 4) no está documentado y no se usa. Valores −999 = faltante. Hay valores iniciales dudosos (p. ej. 358 mm el primer día de la estación 1). |
| MARCO — Cornare (`marco.cornare.gov.co/api/v1`) | `cornare.py` | 32 | 5 min u horaria, desde ~2025 | minutos | Historia corta. Su servidor envía la cadena de certificados incompleta: se resuelve con `truststore` (almacén de certificados de Windows), sin desactivar la verificación SSL. |

### No integradas: requieren descarga manual o solicitud

El programa las lista en la hoja *Descarga manual* (y `estaciones_descarga_manual.shp`) cuando están cerca del proyecto.

| Fuente | Qué hay | Por qué no es automática | Cómo obtenerla |
|---|---|---|---|
| IDEAM convencionales (DHIME) | Series largas (décadas) de pluviómetros y climatológicas | Sin API pública; el portal bloquea acceso automatizado | Descarga manual en atencionciudadano.ideam.gov.co, o solicitud formal al IDEAM |
| SIATA (AMVA) | 228 pluviómetros en el Valle de Aburrá | En línea solo publica valores actuales (`/data/siata_app/Pluviometrica.json`); su portal de descarga ya no existe | Solicitar histórico a SIATA |
| CAR Cundinamarca | 208 estaciones con precipitación (metadatos en ArcGIS `Red_Hidrometereologica_CAR`) | No publica series | Solicitud a la CAR |
| EPM | Red pluviométrica propia | Sin datos abiertos (la capa en SIATA está congelada en 2018) | Solicitud a EPM |
| Cenicafé (FNC) | Red agroclimática cafetera | Solo datos mensuales/anuales en línea | Formulario de solicitud de Cenicafé |
| Corpocaldas / CDIAC | Red de Manizales | Solo boletines PDF | Solicitud |
| Corpourabá, Cortolima, CARDER, Corpoboyacá, DAGMA | — | No se encontraron datos abiertos | Solicitud |

### Evaluadas y descartadas o pendientes

| Fuente | Resultado |
|---|---|
| SAB/IDIGER Bogotá — archivos diarios (`pikt-ntav`, datosabiertos.bogota.gov.co) | Historia 2021-09 a 2025-12 en archivos anuales (formato ancho, coma decimal). No está al día: candidata a complemento histórico. Sus estaciones activas ya entran por `57sv-p2fu`/`s54a-sgyg` cuando el IDEAM las recibe. |
| CVC `avya-p282`, CAM `2jrp-f4m5`, CRQ `nuk6-xevt`, CDMB `57ur-5p28` (datos.gov.co) | Extractos estáticos 2021–2025, no actualizados. Candidatos a complemento histórico. |
| NOAA GHCN-Daily | Solo ~27 aeropuertos de Colombia (los mismos del IDEAM), historia desde 1960 pero congelada desde 2025-08-24 y con muchos huecos. Útil a futuro solo como historia larga de aeropuertos. |
| NOAA GSOD/ISD | Mismo contenido que GHCN-D, congelado desde 2025-08. No útil. |
| Meteostat | Para Colombia, la "precipitación" reciente es de un modelo de pronóstico (DWD MOSMIX), no medida. No usar. |
| OGIMET (SYNOP) | Al día, pero mismos ~27 aeropuertos, requiere decodificar SYNOP y es un servicio personal para uso no comercial. No integrado. |
| CHIRPS / IMERG | Productos grillados (no estaciones). Posible complemento en la fase de procesamiento. |
