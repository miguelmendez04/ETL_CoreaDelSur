# Diagnóstico

Proyecto ETL 2026 · Grupo 6 · Maestría en IA y Ciencia de Datos · Universidad Autónoma de Occidente.

**Pregunta central:** ¿cómo impactará la disminución de la natalidad y el envejecimiento poblacional en la
disponibilidad futura de la fuerza laboral en Corea del Sur?

## 1. El problema

Corea del Sur tiene la fecundidad más baja del mundo y uno de los envejecimientos más rápidos. Las personas que
entrarán a trabajar en los próximos 15 años ya nacieron, así que la caída de nacimientos no es una hipótesis sobre
el futuro: ya está escrita en la pirámide. Lo que el proyecto necesita es una base integrada, trazable y con
calidad medida que permita separar tres cosas que suelen mezclarse: lo que se observó, lo que proyecta KOSTAT y lo
que el equipo supone.

| Usuario | Para qué usa los datos |
|---|---|
| Analistas de política laboral y demográfica | Dimensionar la caída de la población en edad de trabajar y los márgenes de acción |
| Gobiernos regionales | Comparar el riesgo demográfico de su si-do con el resto |
| Investigadores | Reutilizar series homologadas con su linaje hasta la fuente |

## 2. Lo que muestran los datos (resumen)

| Tema | Hallazgo | Nivel de evidencia |
|---|---|---|
| Fecundidad | TFR de 1,48 (2000) a 0,72 (2023), con leve repunte a 0,80 en 2025 | Observado |
| Nacimientos | De 640 mil (2000) a 230 mil (2023) y 254 mil (2025) | Observado |
| Crecimiento natural | Negativo desde 2020 (−32,6 mil); −108,6 mil en 2025, con 363 mil defunciones | Observado |
| Longevidad | Esperanza de vida de 76,0 (2000) a 83,7 años (2024) | Observado |
| Envejecimiento | 65+ de 7,2 % a 20,3 % de la población; dependencia de vejez de 10,1 a 29,3 (2000–2025) | Observado (derivado en el pipeline) |
| Mercado laboral | Población activa de 22,2 a 29,6 millones y participación de 61,2 % a 64,7 %: la mayor participación de mujeres y mayores compensa hoy la caída de jóvenes | Observado |
| Relevo | Desde 2016 entran menos jóvenes de 15-24 que personas de 55-64 (reemplazo laboral 201 en 2000, 58 en 2025) | Observado |
| Población 15-64 | Máximo en 2019 (37,6 millones); 24,4 millones en 2050 (−32 %) y 16,6 millones en 2072 | Proyección oficial KOSTAT (medio) |
| Dependencia futura | Supera 50 en 2036 y 75 en 2049 | Proyección oficial KOSTAT (medio) |
| Migración | La población 15-64 cae entre 28,5 % (migración alta) y 36,8 % (sin migración) a 2050: la migración amortigua, no revierte; en los 8 escenarios de KOSTAT, entre 27,4 % y 36,8 % | Proyección oficial KOSTAT (escenarios de migración) |
| Fuerza laboral potencial | En 2072, entre 19,6 y 22,8 millones según el supuesto (−23 % a −34 % frente a 29,6 millones en 2025) | Escenario propio (A/B/C/D) |
| Regiones | Mayor riesgo: Gyeongsangbuk-do, Busan y Jeonbuk; menor: Sejong, el único si-do cuya población 15-64 crece | Inferencia propia (índice descriptivo) |

El detalle por pregunta de negocio está en el notebook `06_resultados_gold.ipynb` y en los tableros.

## 3. Hallazgos del perfilamiento de las fuentes y cómo se resolvieron

Los notebooks `01` a `05` perfilan cada fuente (cobertura, nulos, unidades, duplicados, contraste). Lo que
encontraron y lo que se hizo:

| # | Hallazgo | Impacto si no se trata | Resolución en el pipeline |
|---|---|---|---|
| H1 | La población de KOSIS 2023–2025 sale de las tablas de proyección (DT_1BPA001/DT_1BPB001) | Se presentaría proyección como observación | Esos años se marcan `estado = preliminar`; las vistas gold llevan `tipo_dato` (`observado`, `preliminar`, `proyeccion_oficial`, `escenario_propio`) |
| H2 | Los escenarios "alto/bajo" del archivo de KOSTAT son variantes de solo fecundidad; el archivo trae 28 variantes y no el medio puro | Etiquetarlos como compuestos sería engañoso | Medio desde la tabla nacional; alto/bajo = fecundidad; se agregan los 3 escenarios de migración; el resto queda en bronze |
| H3 | La EAPS publica en miles y se redondea | Totales que "no cuadran" por redondeo | Conversión a personas y tolerancia de coherencia con margen de redondeo |
| H4 | Sejong existe desde 2012 y la EAPS lo publica desde 2017 | Series regionales no comparables | Agregado Chungnam + Sejong; los vacíos previos a su creación son "no aplica", no rechazos |
| H5 | "Jeonnam-Gwangju" aparece solo en 2025 (= Gwangju + Jeollanam-do) | Duplicaría valores | Se excluye con motivo trazado (208 rechazos) |
| H6 | Gangwon y Jeonbuk cambiaron de nombre oficial | Dos territorios donde hay uno | `dim_territorio` guarda ambos códigos |
| H7 | Las etiquetas de KOSIS vienen en inglés y en coreano (`남자`, `0 - 4세`, `중위 추계`) | Filas sin homologar | Diccionario explícito `etiquetas.csv` |
| H8 | La OCDE mide la dependencia de vejez como 65+/20-64 | Contraste no comparable | Queda en bronze; la dependencia se calcula en el pipeline y se concilia con el WB |
| H9 | La EAPS excluye militares y población institucional | La fuerza laboral proyectada no reproduciría la observada | Factor de cobertura EAPS/KOSTAT por sexo y edad en el año base |
| H10 | La OpenAPI de KOSIS está restringida a residentes de Corea | No se puede automatizar KOSIS | Descarga manual documentada; el extractor verifica encoding, columnas y años, y avisa qué falta |
| H11 | La OCDE publica participación en 15-24, 25-54 y 55-64; la EAPS en grupos decenales | El supuesto C no tiene objetivo directo | Equivalencias ponderadas documentadas; 15-19 y 60+ constantes |
| H12 | UN WPP difiere de KOSTAT en proyección hasta 44 % (grupo 0-14 en los escenarios de fecundidad) | Se leería como error de datos | Se guarda como contraste; el KPI de ±3 % se mide solo en el histórico |

## 4. Alcance

**Dentro:** histórico 2000–2025 nacional y por si-do; proyección oficial de KOSTAT (nacional 2026–2072,
si-do 2026–2052); comparación con países OCDE; escenarios propios de fuerza laboral; índice de riesgo por si-do;
KPIs de calidad; tableros en Power BI y HTML; orquestación con Airflow.

**Fuera:** pronósticos propios (el ETL no proyecta población), relaciones causales (las asociaciones son
correlaciones), datos administrativos del Ministerio de Empleo y Trabajo y flujos migratorios observados (la
migración se analiza con los escenarios oficiales de KOSTAT).

## 5. Objetivos y cómo se cumplen

| Objetivo | Evidencia |
|---|---|
| Integrar ≥ 3 fuentes institucionales con una maestra por indicador | 4 fuentes, 25 datasets; [fuentes_datos.md](fuentes_datos.md) |
| Separar histórico, proyección oficial y escenario propio | Tablas distintas y `tipo_dato`; [02_diseno.md](02_diseno.md) |
| Medir la calidad con umbrales realistas | 13 KPIs en `ctl.kpis`, todos cumplidos; [03_validacion.md](03_validacion.md) |
| Trazabilidad de cada valor hasta el archivo crudo | `id_carga_origen`, `ctl.log_cargas`, sha256; [linaje_datos.md](linaje_datos.md) |
| Responder las 10 preguntas de negocio | Una tabla o vista gold por pregunta (1–9) y el informe (10) |
| Documentar todos los indicadores y columnas | [diccionario_datos.md](diccionario_datos.md), generado desde la base |
