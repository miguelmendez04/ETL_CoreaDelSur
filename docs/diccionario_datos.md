# Diccionario de datos

Generado con `python -m src.quality.diccionario` desde el esquema real de PostgreSQL (`information_schema`). Las descripciones están en `config/mappings/tablas.csv` y `columnas.csv`; los indicadores, en `silver.dim_indicador` (`config/mappings/indicadores.csv`). No editar a mano.

- Tablas y vistas: 34 (23 tablas, 11 vistas).
- Columnas: 316, documentadas el 100 %.
- Indicadores: 16 (3 calculados en el pipeline).

## Indicadores

| cod_indicador | nombre | definicion | unidad | frecuencia_original | fuente_maestra | fuente_contraste | es_derivado | rango_min | rango_max |
|---|---|---|---|---|---|---|---|---|---|
| CRECIMIENTO_NATURAL | Crecimiento natural | Nacimientos menos defunciones (negativo desde 2020) | personas | anual | KOSIS |  | no |  |  |
| DEFUNCIONES | Defunciones | Defunciones registradas en el año | personas | anual | KOSIS |  | no | 0 |  |
| ESPERANZA_VIDA | Esperanza de vida al nacer | Años que viviría en promedio un recién nacido con la mortalidad del año | años | anual | KOSIS |  | no | 0 | 120 |
| NACIMIENTOS | Nacimientos | Nacidos vivos registrados en el año | personas | anual | KOSIS | OECD;WB | no | 0 |  |
| OCUPADOS | Ocupados | Personas ocupadas de 15 años y más (promedio anual de la EAPS) | personas | mensual | KOSIS | OECD | no | 0 |  |
| PIB_HORA | PIB por hora trabajada | PIB por hora trabajada en USD PPA constantes | USD PPA const. | anual | OECD |  | no | 0 |  |
| PIB_OCUPADO | PIB por ocupado | PIB por persona ocupada en USD PPA constantes de 2021 (comparación internacional) | USD PPA const. | anual | WB |  | no | 0 |  |
| POB_15MAS | Población de 15 años y más | Población civil de 15 años y más cubierta por la EAPS (promedio anual) | personas | mensual | KOSIS |  | no | 0 |  |
| POB_ACTIVA | Población económicamente activa | Ocupados + desocupados de 15 años y más (promedio anual de la EAPS) | personas | mensual | KOSIS | OECD | no | 0 |  |
| POBLACION | Población | Población estimada a mitad de año por sexo y edad | personas | anual | KOSIS | UNWPP;WB | no | 0 |  |
| TASA_DESEMPLEO | Tasa de desempleo | Desocupados / población activa × 100 | % | mensual | KOSIS | OECD | no | 0 | 100 |
| TASA_PARTICIPACION | Tasa de participación | Población activa / población de 15 años y más × 100 | % | mensual | KOSIS | WB | no | 0 | 100 |
| TFR | Tasa global de fecundidad | Número medio de hijos por mujer al final de su vida reproductiva | hijos por mujer | anual | KOSIS | OECD;WB | no | 0 | 10 |
| DEPENDENCIA_VEJEZ | Tasa de dependencia de vejez | Pob 65+ / pob 15-64 × 100 | ratio × 100 | anual | PIPELINE | WB | sí | 0 |  |
| INDICE_ENVEJECIMIENTO | Índice de envejecimiento | Pob 65+ / pob 0-14 × 100 | ratio × 100 | anual | PIPELINE | WB | sí | 0 |  |
| PROP_65MAS | Proporción de 65+ | Pob 65+ / pob total × 100 | % | anual | PIPELINE | WB | sí | 0 | 100 |

## Tablas y vistas

| esquema | tabla | objeto | descripcion | grano | clave_primaria | columnas |
|---|---|---|---|---|---|---|
| bronze | bronze.kosis | tabla | CSV de KOSIS tal como se descargaron (cada fila del CSV en JSONB) | una fila por fila del archivo crudo | id_bronze | 11 |
| bronze | bronze.oecd_sdmx | tabla | Respuesta SDMX de la OCDE sin modificar | una fila por observación de la respuesta | id_bronze | 9 |
| bronze | bronze.unwpp_wpp2024 | tabla | Respuesta de la API de UN WPP 2024 sin modificar | una fila por observación de la respuesta | id_bronze | 9 |
| bronze | bronze.worldbank_wdi | tabla | Respuesta de la API del Banco Mundial (WDI) sin modificar | una fila por observación de la respuesta | id_bronze | 9 |
| silver | silver.conciliacion | tabla | Maestra vs contraste con su diferencia; el contraste nunca reemplaza el valor maestro | nivel × anio × territorio × sexo × grupo de edad × indicador × escenario × fuente de contraste | nivel, anio, cod_territorio, sexo, grupo_edad, cod_indicador, escenario, fuente_contraste | 14 |
| silver | silver.dim_edad | tabla | Grupos de edad: quinquenales, decenales de la EAPS, agregados 0-14 / 15-64 / 65+ y TOTAL | una fila por grupo de edad | cod_grupo_edad | 5 |
| silver | silver.dim_indicador | tabla | Diccionario de indicadores: definición, unidad, frecuencia, fuente maestra y de contraste, rango válido | una fila por indicador | cod_indicador | 10 |
| silver | silver.dim_sexo | tabla | Sexo homologado entre fuentes | una fila por sexo (T, H, M) | cod_sexo | 5 |
| silver | silver.dim_territorio | tabla | Territorios homologados: nacional, 17 si-do, agregado Chungnam+Sejong, países y agregados internacionales | una fila por territorio | cod_territorio | 11 |
| silver | silver.fact_historico | tabla | Histórico observado 2000-2025 en formato largo (fuente maestra + indicadores derivados) | anio × territorio × sexo × grupo de edad × indicador | anio, cod_territorio, sexo, grupo_edad, cod_indicador | 12 |
| silver | silver.fact_proyeccion | tabla | Proyecciones oficiales de KOSTAT sin modificar | anio × territorio × sexo × grupo de edad × indicador × edición × escenario | anio, cod_territorio, sexo, grupo_edad, cod_indicador, edicion_proyeccion, escenario | 14 |
| gold | gold.asociaciones | tabla | Correlación (no causalidad) entre envejecimiento, empleo y productividad 2000-2025 | par de variables | variable_x, variable_y | 8 |
| gold | gold.escenario_fuerza_laboral | tabla | Fuerza laboral potencial = población KOSTAT × factor de cobertura × tasa supuesta (escenario propio, no pronóstico) | anio × escenario KOSTAT × supuesto × sexo × grupo de edad EAPS | anio, escenario_kostat, id_supuesto, version_modelo, sexo, grupo_edad | 11 |
| gold | gold.escenarios_sensibilidad | tabla | Fuerza laboral total con variantes de los parámetros de B, C y D (escenario KOSTAT medio) | supuesto × variante × anio | id_supuesto, variante, anio | 5 |
| gold | gold.hitos_escasez | tabla | Años en que se cruzan umbrales de escasez laboral y cambio de la fuerza laboral por escenario | hito × escenario KOSTAT × supuesto | hito, escenario_kostat, id_supuesto | 7 |
| gold | gold.indicadores_riesgo | tabla | Índice de riesgo demográfico por si-do (0-100, descriptivo, no causal) | una fila por si-do | cod_territorio | 15 |
| gold | gold.riesgo_sensibilidad | tabla | Ranking de riesgo con otros pesos y normalizaciones | si-do × esquema | cod_territorio, esquema | 5 |
| gold | gold.supuestos | tabla | Supuestos de los escenarios propios A/B/C/D con sus parámetros (versionados) | id_supuesto × version_modelo | id_supuesto, version_modelo | 6 |
| gold | gold.v_anios | vista | Dimensión de años para Power BI (histórico y proyección) | una fila por año |  | 1 |
| gold | gold.v_calidad_dataset | vista | Calidad por dataset de la última ejecución de silver (con tasas de válidos y de rechazo) | una fila por fuente × dataset |  | 8 |
| gold | gold.v_conciliacion | vista | Conciliación con el nombre del indicador y la marca de tolerancia ±3 % | igual que silver.conciliacion |  | 16 |
| gold | gold.v_embudo_silver | vista | Embudo bronze -> silver de la última ejecución | una fila por paso |  | 8 |
| gold | gold.v_escenarios_resumen | vista | Fuerza laboral potencial total país por escenario y supuesto | anio × escenario KOSTAT × supuesto |  | 10 |
| gold | gold.v_kpis_calidad | vista | KPIs de calidad de la última ejecución | una fila por KPI |  | 6 |
| gold | gold.v_natalidad_vs_15_64 | vista | Nacimientos frente a la población 15-19 y 15-64 (cohortes que entran a la edad de trabajar) | una fila por año |  | 9 |
| gold | gold.v_panel_indicadores | vista | Panel anual por territorio con una columna por indicador (histórico + proyección media) | nivel × anio × territorio |  | 26 |
| gold | gold.v_proyeccion_escenarios | vista | Proyección oficial nacional por escenario de fecundidad y de migración | anio × escenario |  | 6 |
| gold | gold.v_senales_escasez | vista | Señales tempranas de escasez laboral por año y territorio | nivel × anio × territorio |  | 11 |
| gold | gold.v_territorios | vista | Dimensión de territorio para Power BI | una fila por territorio |  | 6 |
| ctl | ctl.calidad_dataset | tabla | Registros evaluados, válidos y rechazados por dataset de bronze en cada ejecución de silver | una fila por carga × fuente × dataset | id_carga, fuente, dataset | 6 |
| ctl | ctl.kpis | tabla | Foto de los KPIs de calidad de cada ejecución | una fila por carga × KPI | id_carga, kpi | 6 |
| ctl | ctl.log_cargas | tabla | Bitácora de cada ejecución y dataset: inicio, fin, estado y filas extraídas, válidas y rechazadas | una fila por ejecución × dataset (id_carga) | id_carga | 15 |
| ctl | ctl.pasos_silver | tabla | Embudo bronze -> silver: filas después de cada paso de filtro o de cálculo | una fila por carga × paso | id_carga, orden | 8 |
| ctl | ctl.rechazos | tabla | Registros que no pasan las validaciones bronze -> silver, con la regla y el motivo | una fila por registro rechazado | id_rechazo | 8 |

## Columnas: Bronze (`bronze`)

### bronze.kosis

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_bronze | bigint | PK | no | Identificador del registro en bronze |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| org_id | text |  | sí | Organismo emisor en KOSIS (101 = KOSTAT) |
| tbl_id | text |  | sí | Identificador de la tabla en KOSIS |
| url | text |  | no | URL de la tabla o de la solicitud a la API |
| params | jsonb |  | sí | Parámetros de la solicitud o del archivo (JSON: archivo, encoding, formato, dataflow) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| registro | jsonb |  | no | Registro original sin modificar (JSON) |
| hash_registro | text |  | no | sha256 del registro (monitoreo de duplicados en bronze) |

### bronze.oecd_sdmx

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_bronze | bigint | PK | no | Identificador del registro en bronze |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| url | text |  | no | URL de la tabla o de la solicitud a la API |
| params | jsonb |  | sí | Parámetros de la solicitud o del archivo (JSON: archivo, encoding, formato, dataflow) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| registro | jsonb |  | no | Registro original sin modificar (JSON) |
| hash_registro | text |  | no | sha256 del registro (monitoreo de duplicados en bronze) |

### bronze.unwpp_wpp2024

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_bronze | bigint | PK | no | Identificador del registro en bronze |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| url | text |  | no | URL de la tabla o de la solicitud a la API |
| params | jsonb |  | sí | Parámetros de la solicitud o del archivo (JSON: archivo, encoding, formato, dataflow) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| registro | jsonb |  | no | Registro original sin modificar (JSON) |
| hash_registro | text |  | no | sha256 del registro (monitoreo de duplicados en bronze) |

### bronze.worldbank_wdi

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_bronze | bigint | PK | no | Identificador del registro en bronze |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| url | text |  | no | URL de la tabla o de la solicitud a la API |
| params | jsonb |  | sí | Parámetros de la solicitud o del archivo (JSON: archivo, encoding, formato, dataflow) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| registro | jsonb |  | no | Registro original sin modificar (JSON) |
| hash_registro | text |  | no | sha256 del registro (monitoreo de duplicados en bronze) |

## Columnas: Silver (`silver`)

### silver.conciliacion

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| nivel | text | PK | no | historico (observado) o proyeccion (oficial KOSTAT) |
| anio | smallint | PK | no | Año de la observación (frecuencia anual común) |
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| sexo | text | PK | no | Sexo: T, H o M (ver silver.dim_sexo) |
| grupo_edad | text | PK | no | Grupo de edad (ver silver.dim_edad) |
| cod_indicador | text | PK | no | Código del indicador (ver silver.dim_indicador) |
| escenario | text | PK | no | Escenario de la proyección (NA en el histórico) |
| fuente_maestra | text |  | no | Fuente maestra del indicador |
| fuente_contraste | text | PK | no | Fuentes usadas solo para contrastar |
| valor_maestra | numeric |  | no | Valor de la fuente maestra |
| valor_contraste | numeric |  | no | Valor de la fuente de contraste |
| dif_abs | numeric |  | sí | Diferencia absoluta: contraste - maestra |
| dif_pct | numeric |  | sí | Diferencia porcentual: (contraste - maestra) / maestra × 100 |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### silver.dim_edad

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_grupo_edad | text | PK | no | Código del grupo de edad (p. ej. 0-4, 15-64, 65+, TOTAL) |
| edad_min | smallint |  | no | Edad mínima del grupo |
| edad_max | smallint |  | sí | Edad máxima del grupo (vacío = grupo abierto) |
| tipo | text |  | no | Tipo de grupo: total, quinquenal, decenal (EAPS) o agregado |
| orden | smallint |  | no | Orden de presentación |

### silver.dim_indicador

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_indicador | text | PK | no | Código del indicador (ver silver.dim_indicador) |
| nombre | text |  | no | Nombre legible |
| definicion | text |  | no | Definición del indicador |
| unidad | text |  | no | Unidad de medida |
| frecuencia_original | text |  | no | Frecuencia publicada por la fuente (anual, trimestral o mensual) |
| fuente_maestra | text |  | no | Fuente maestra del indicador |
| fuente_contraste | text |  | sí | Fuentes usadas solo para contrastar |
| es_derivado | boolean |  | no | Si el indicador se calcula en el pipeline y no se toma de una fuente |
| rango_min | numeric |  | sí | Valor mínimo válido (validación de rango) |
| rango_max | numeric |  | sí | Valor máximo válido (validación de rango) |

### silver.dim_sexo

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_sexo | text | PK | no | Código de sexo: T (total), H (hombres), M (mujeres) |
| nombre | text |  | no | Nombre legible |
| cod_kosis | text |  | sí | Etiqueta del sexo en KOSIS |
| cod_worldbank | text |  | sí | Código del sexo en el Banco Mundial |
| cod_oecd | text |  | sí | Código del sexo en la OCDE |

### silver.dim_territorio

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| nombre_es | text |  | no | Nombre en español |
| nombre_en | text |  | sí | Nombre en inglés |
| nombre_ko | text |  | sí | Nombre en coreano |
| tipo | text |  | no | Tipo de territorio: nacional, sido, agregado, pais o agregado_int |
| cod_kosis | text |  | sí | Código o etiqueta del territorio en KOSIS |
| cod_kosis_alt | text |  | sí | Código nuevo tras el cambio de nombre oficial (Gangwon, Jeonbuk) |
| iso3 | text |  | sí | Código ISO3 del país |
| vigente_desde | smallint |  | sí | Primer año en que existe el territorio |
| vigente_hasta | smallint |  | sí | Último año en que existe el territorio |
| observacion | text |  | sí | Notas de homologación del territorio |

### silver.fact_historico

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint | PK | no | Año de la observación (frecuencia anual común) |
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| sexo | text | PK | no | Sexo: T, H o M (ver silver.dim_sexo) |
| grupo_edad | text | PK | no | Grupo de edad (ver silver.dim_edad) |
| cod_indicador | text | PK | no | Código del indicador (ver silver.dim_indicador) |
| valor | numeric |  | no | Valor del indicador en la unidad de silver.dim_indicador |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| version_publicacion | text |  | sí | Versión o fecha de publicación de la fuente |
| estado | text |  | no | preliminar o definitivo, según la publicación de la fuente |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| id_carga_origen | bigint |  | sí | Carga bronze de la que viene la fila (vacío si es derivada) |

### silver.fact_proyeccion

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint | PK | no | Año de la observación (frecuencia anual común) |
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| sexo | text | PK | no | Sexo: T, H o M (ver silver.dim_sexo) |
| grupo_edad | text | PK | no | Grupo de edad (ver silver.dim_edad) |
| cod_indicador | text | PK | no | Código del indicador (ver silver.dim_indicador) |
| edicion_proyeccion | text | PK | no | Edición de la proyección de KOSTAT (KOSTAT_2022_2072 nacional, KOSTAT_2022_2052 si-do) |
| escenario | text | PK | no | Escenario de KOSTAT: medio, alto, bajo (fecundidad) o sin_migracion, migracion_baja, migracion_alta |
| valor | numeric |  | no | Valor del indicador en la unidad de silver.dim_indicador |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| fecha_extraccion | timestamp with time zone |  | no | Fecha y hora de la extracción (America/Bogota) |
| version_publicacion | text |  | sí | Versión o fecha de publicación de la fuente |
| estado | text |  | no | preliminar o definitivo, según la publicación de la fuente |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| id_carga_origen | bigint |  | sí | Carga bronze de la que viene la fila (vacío si es derivada) |

## Columnas: Gold (`gold`)

### gold.asociaciones

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| variable_x | text | PK | no | Primera variable del par |
| variable_y | text | PK | no | Segunda variable del par |
| anio_inicio | smallint |  | no | Primer año usado en el cálculo |
| anio_fin | smallint |  | no | Último año usado en el cálculo |
| n | smallint |  | no | Número de años con dato en ambas series |
| corr_niveles | numeric |  | sí | Correlación de Pearson en niveles (las series con tendencia suelen correlacionar) |
| corr_variaciones | numeric |  | sí | Correlación de Pearson de las variaciones anuales (si se mueven juntas año a año) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.escenario_fuerza_laboral

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint | PK | no | Año de la observación (frecuencia anual común) |
| escenario_kostat | text | PK | no | Escenario de fecundidad de KOSTAT sobre el que se calcula el supuesto propio |
| id_supuesto | text | PK | no | Supuesto propio: A constante, B tendencia con tope, C convergencia OCDE, D cierre de brecha de género ('-' si no aplica) |
| version_modelo | text | PK | no | Versión del modelo de escenarios (config.yaml) |
| sexo | text | PK | no | Sexo: T, H o M (ver silver.dim_sexo) |
| grupo_edad | text | PK | no | Grupo de edad (ver silver.dim_edad) |
| poblacion | numeric |  | no | Población proyectada por KOSTAT para el sexo y grupo (personas) |
| factor_cobertura | numeric |  | no | Población 15+ de la EAPS / población KOSTAT del mismo sexo y grupo en el año base (la EAPS excluye militares y población institucional) |
| tasa_participacion | numeric |  | no | Tasa de participación supuesta para ese año (%) |
| fuerza_laboral | numeric |  | no | Fuerza laboral potencial (personas) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.escenarios_sensibilidad

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_supuesto | text | PK | no | Supuesto propio: A constante, B tendencia con tope, C convergencia OCDE, D cierre de brecha de género ('-' si no aplica) |
| variante | text | PK | no | Variante de los parámetros probada en la sensibilidad |
| anio | smallint | PK | no | Año de la observación (frecuencia anual común) |
| fuerza_laboral | numeric |  | no | Fuerza laboral potencial (personas) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.hitos_escasez

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| hito | text | PK | no | Nombre del hito de escasez laboral |
| escenario_kostat | text | PK | no | Escenario de fecundidad de KOSTAT sobre el que se calcula el supuesto propio |
| id_supuesto | text | PK | no | Supuesto propio: A constante, B tendencia con tope, C convergencia OCDE, D cierre de brecha de género ('-' si no aplica) |
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| valor | numeric |  | sí | Valor del indicador en el año del hito (o cambio %) |
| descripcion | text |  | no | Descripción en lenguaje natural |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.indicadores_riesgo

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| anio_base | smallint |  | no | Año base del cálculo (último año observado: 2025) |
| anio_proyeccion | smallint |  | no | Año de la proyección KOSTAT usado en el índice (2052) |
| prop_65mas | numeric |  | sí | Proporción de población de 65+ (%) |
| tfr | numeric |  | sí | Tasa global de fecundidad (hijos por mujer) |
| dependencia_vejez | numeric |  | sí | Dependencia de vejez: población 65+ / población 15-64 × 100 (calculada en el pipeline) |
| indice_envejecimiento | numeric |  | sí | Índice de envejecimiento: población 65+ / población 0-14 × 100 (calculado en el pipeline) |
| tasa_participacion | numeric |  | sí | Tasa de participación 15+ (%) |
| var_pob_15_64_hist_pct | numeric |  | sí | Cambio % de la población 15-64 entre 2015 y el año base |
| var_pob_15_64_proy_pct | numeric |  | sí | Cambio % de la población 15-64 entre el año base y el de proyección (KOSTAT medio) |
| dependencia_vejez_proy | numeric |  | sí | Dependencia de vejez proyectada por KOSTAT en el año de proyección (escenario medio) |
| indice_riesgo | numeric |  | no | Índice de riesgo demográfico (0 = menor riesgo y 100 = mayor entre los 17 si-do en min-max; puntaje estándar en z-score) |
| ranking | smallint |  | no | Puesto en el índice de riesgo (1 = mayor riesgo) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| reemplazo_laboral | numeric |  | sí | Reemplazo laboral: población 15-24 por cada 100 de 55-64 |

### gold.riesgo_sensibilidad

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_territorio | text | PK | no | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| esquema | text | PK | no | Esquema de sensibilidad del índice de riesgo (pesos y normalización, ver config.yaml) |
| indice_riesgo | numeric |  | no | Índice de riesgo demográfico (0 = menor riesgo y 100 = mayor entre los 17 si-do en min-max; puntaje estándar en z-score) |
| ranking | smallint |  | no | Puesto en el índice de riesgo (1 = mayor riesgo) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.supuestos

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_supuesto | text | PK | no | Supuesto propio: A constante, B tendencia con tope, C convergencia OCDE, D cierre de brecha de género ('-' si no aplica) |
| version_modelo | text | PK | no | Versión del modelo de escenarios (config.yaml) |
| nombre | text |  | no | Nombre legible |
| descripcion | text |  | no | Descripción en lenguaje natural |
| parametros | jsonb |  | no | Parámetros del supuesto y valores calculados (JSON) |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |

### gold.v_anios

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |

### gold.v_calidad_dataset

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint |  | sí | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text |  | sí | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | sí | Nombre del dataset en config.yaml (o código del indicador WDI) |
| registros_evaluados | integer |  | sí | Registros del dataset que pasaron por las reglas (válidos + rechazados) |
| registros_validos | integer |  | sí | Registros del dataset que pasaron todas las reglas |
| registros_rechazados | integer |  | sí | Registros del dataset enviados a ctl.rechazos |
| tasa_validos_pct | numeric |  | sí | Registros válidos / evaluados × 100 |
| tasa_rechazo_pct | numeric |  | sí | Registros rechazados / evaluados × 100 |

### gold.v_conciliacion

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| nivel | text |  | sí | historico (observado) o proyeccion (oficial KOSTAT) |
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| cod_territorio | text |  | sí | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| sexo | text |  | sí | Sexo: T, H o M (ver silver.dim_sexo) |
| grupo_edad | text |  | sí | Grupo de edad (ver silver.dim_edad) |
| cod_indicador | text |  | sí | Código del indicador (ver silver.dim_indicador) |
| escenario | text |  | sí | Escenario de la proyección (NA en el histórico) |
| fuente_maestra | text |  | sí | Fuente maestra del indicador |
| fuente_contraste | text |  | sí | Fuentes usadas solo para contrastar |
| valor_maestra | numeric |  | sí | Valor de la fuente maestra |
| valor_contraste | numeric |  | sí | Valor de la fuente de contraste |
| dif_abs | numeric |  | sí | Diferencia absoluta: contraste - maestra |
| dif_pct | numeric |  | sí | Diferencia porcentual: (contraste - maestra) / maestra × 100 |
| id_carga | bigint |  | sí | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| indicador | text |  | sí | Nombre legible del indicador |
| dentro_tolerancia | boolean |  | sí | Si la diferencia maestra vs contraste está dentro de ±3 % |

### gold.v_embudo_silver

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint |  | sí | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| orden | smallint |  | sí | Orden de presentación |
| paso | text |  | sí | Paso del embudo bronze -> silver |
| tipo | text |  | sí | filtro (deja pasar o descarta filas) o calculo (agrega filas calculadas) |
| filas | integer |  | sí | Filas después del paso |
| variacion | integer |  | sí | Filas del paso menos filas del paso anterior (negativo = descartadas) |
| en_embudo | boolean |  | sí | Si el paso forma parte del embudo decreciente (filtros antes del primer cálculo) |
| descripcion | text |  | sí | Descripción en lenguaje natural |

### gold.v_escenarios_resumen

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| escenario_kostat | text |  | sí | Escenario de fecundidad de KOSTAT sobre el que se calcula el supuesto propio |
| id_supuesto | text |  | sí | Supuesto propio: A constante, B tendencia con tope, C convergencia OCDE, D cierre de brecha de género ('-' si no aplica) |
| supuesto | text |  | sí | Nombre del supuesto propio |
| version_modelo | text |  | sí | Versión del modelo de escenarios (config.yaml) |
| fuerza_laboral | numeric |  | sí | Fuerza laboral potencial (personas) |
| poblacion_15mas | numeric |  | sí | Población proyectada de 15+ (personas) |
| tasa_participacion_agregada | numeric |  | sí | Fuerza laboral / población 15+ × 100 (%) |
| pob_15_64 | numeric |  | sí | Población de 15-64 años (personas) |
| tipo_dato | text |  | sí | Naturaleza del dato: observado, preliminar, proyeccion_oficial o escenario_propio |

### gold.v_kpis_calidad

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint |  | sí | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| kpi | text |  | sí | Nombre del KPI de calidad |
| valor | numeric |  | sí | Valor del indicador en la unidad de silver.dim_indicador |
| meta | text |  | sí | Meta del KPI |
| cumple | boolean |  | sí | Si el KPI alcanza la meta |
| detalle | text |  | sí | Cómo se calculó el KPI (numerador y denominador) |

### gold.v_natalidad_vs_15_64

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| nivel | text |  | sí | historico (observado) o proyeccion (oficial KOSTAT) |
| nacimientos | numeric |  | sí | Nacidos vivos (personas) |
| pob_15_19 | numeric |  | sí | Población de 15-19 años (personas) |
| pob_15_64 | numeric |  | sí | Población de 15-64 años (personas) |
| var_pob_15_64_pct | numeric |  | sí | Cambio % de la población 15-64 respecto al año anterior |
| nacidos_hace_15 | numeric |  | sí | Nacidos en t-15 |
| nacidos_cohorte_15_19 | numeric |  | sí | Nacidos entre t-19 y t-15 (la cohorte que en t tiene 15-19 años) |
| pct_cohorte_presente | numeric |  | sí | Población 15-19 / nacidos de su cohorte × 100 (supervivencia y migración neta) |

### gold.v_panel_indicadores

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| nivel | text |  | sí | historico (observado) o proyeccion (oficial KOSTAT) |
| escenario | text |  | sí | observado (histórico) o el escenario de KOSTAT de la proyección |
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| cod_territorio | text |  | sí | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| territorio | text |  | sí | Nombre del territorio en español |
| tipo_territorio | text |  | sí | Tipo de territorio (ver silver.dim_territorio) |
| tfr | numeric |  | sí | Tasa global de fecundidad (hijos por mujer) |
| nacimientos | numeric |  | sí | Nacidos vivos (personas) |
| poblacion_total | numeric |  | sí | Población total (personas) |
| pob_0_14 | numeric |  | sí | Población de 0-14 años (personas) |
| pob_15_64 | numeric |  | sí | Población de 15-64 años (personas) |
| pob_65mas | numeric |  | sí | Población de 65 años y más (personas) |
| prop_65mas | numeric |  | sí | Proporción de población de 65+ (%) |
| indice_envejecimiento | numeric |  | sí | Índice de envejecimiento: población 65+ / población 0-14 × 100 (calculado en el pipeline) |
| dependencia_vejez | numeric |  | sí | Dependencia de vejez: población 65+ / población 15-64 × 100 (calculada en el pipeline) |
| pob_activa | numeric |  | sí | Población económicamente activa de 15+ (personas) |
| ocupados | numeric |  | sí | Población ocupada de 15+ (personas) |
| tasa_participacion | numeric |  | sí | Tasa de participación 15+ (%) |
| tasa_desempleo | numeric |  | sí | Tasa de desempleo 15+ (%) |
| pib_hora | numeric |  | sí | PIB por hora trabajada (USD PPA constantes; OCDE) |
| pib_ocupado | numeric |  | sí | PIB por persona ocupada (USD PPA constantes) |
| tiene_preliminares | boolean |  | sí | Si alguno de los valores de la fila es preliminar |
| defunciones | numeric |  | sí | Defunciones registradas en el año (personas) |
| crecimiento_natural | numeric |  | sí | Nacimientos menos defunciones (personas; negativo desde 2020) |
| esperanza_vida | numeric |  | sí | Esperanza de vida al nacer (años) |
| tipo_dato | text |  | sí | Naturaleza del dato: observado, preliminar, proyeccion_oficial o escenario_propio |

### gold.v_proyeccion_escenarios

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| escenario | text |  | sí | Escenario de KOSTAT (fecundidad o migración) |
| pob_15_64 | numeric |  | sí | Población de 15-64 años (personas) |
| pob_65mas | numeric |  | sí | Población de 65 años y más (personas) |
| dependencia_vejez | numeric |  | sí | Dependencia de vejez: población 65+ / población 15-64 × 100 (calculada en el pipeline) |
| tipo_dato | text |  | sí | Naturaleza del dato: observado, preliminar, proyeccion_oficial o escenario_propio |

### gold.v_senales_escasez

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| nivel | text |  | sí | historico (observado) o proyeccion (oficial KOSTAT) |
| anio | smallint |  | sí | Año de la observación (frecuencia anual común) |
| cod_territorio | text |  | sí | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| territorio | text |  | sí | Nombre del territorio en español |
| tipo_territorio | text |  | sí | Tipo de territorio (ver silver.dim_territorio) |
| relevo_generacional | numeric |  | sí | Relevo generacional: población 15-19 por cada 100 de 60-64 |
| pob_15_64 | numeric |  | sí | Población de 15-64 años (personas) |
| var_pob_15_64_pct | numeric |  | sí | Cambio % de la población 15-64 respecto al año anterior |
| dependencia_vejez | numeric |  | sí | Dependencia de vejez: población 65+ / población 15-64 × 100 (calculada en el pipeline) |
| tasa_desempleo | numeric |  | sí | Tasa de desempleo 15+ (%) |
| reemplazo_laboral | numeric |  | sí | Reemplazo laboral: población 15-24 por cada 100 de 55-64 |

### gold.v_territorios

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| cod_territorio | text |  | sí | Código del territorio: 00 nacional, códigos KOSIS de si-do, ISO3 para países (ver silver.dim_territorio) |
| territorio | text |  | sí | Nombre del territorio en español |
| nombre_en | text |  | sí | Nombre en inglés |
| tipo | text |  | sí | Tipo de territorio: nacional, sido, agregado, pais o agregado_int |
| iso3 | text |  | sí | Código ISO3 del país |
| orden_tipo | integer |  | sí | Orden del tipo de territorio para Power BI |

## Columnas: Control (`ctl`)

### ctl.calidad_dataset

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint | PK | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| fuente | text | PK | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text | PK | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| registros_evaluados | integer |  | no | Registros del dataset que pasaron por las reglas (válidos + rechazados) |
| registros_validos | integer |  | no | Registros del dataset que pasaron todas las reglas |
| registros_rechazados | integer |  | no | Registros del dataset enviados a ctl.rechazos |

### ctl.kpis

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint | PK | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| kpi | text | PK | no | Nombre del KPI de calidad |
| valor | numeric |  | sí | Valor del KPI |
| meta | text |  | no | Meta del KPI |
| cumple | boolean |  | no | Si el KPI alcanza la meta |
| detalle | text |  | sí | Cómo se calculó el KPI (numerador y denominador) |

### ctl.log_cargas

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint | PK | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| capa | text |  | no | Capa del pipeline: bronze, silver o gold |
| fuente | text |  | no | Fuente del dato (KOSIS, OECD, WB, UNWPP o PIPELINE si es derivado) |
| dataset | text |  | no | Nombre del dataset en config.yaml (o código del indicador WDI) |
| parametros | jsonb |  | sí | Parámetros de la extracción (JSON) |
| inicio | timestamp with time zone |  | no | Inicio de la ejecución |
| fin | timestamp with time zone |  | sí | Fin de la ejecución |
| estado | text |  | no | Estado de la ejecución: en_curso, exito, fallo u omitido (crudo idéntico al de la última carga) |
| metodo | text |  | sí | Método de obtención: api, descarga_manual o pipeline |
| archivo | text |  | sí | Archivo crudo en data/bronze/<fuente>/<fecha>/ |
| hash_archivo | text |  | sí | sha256 del contenido crudo (detecta descargas idénticas) |
| filas_extraidas | integer |  | sí | Filas leídas del crudo |
| filas_validas | integer |  | sí | Filas que pasaron las validaciones |
| filas_rechazadas | integer |  | sí | Filas enviadas a ctl.rechazos |
| mensaje_error | text |  | sí | Error técnico si la ejecución falló |

### ctl.pasos_silver

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_carga | bigint | PK | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| orden | smallint | PK | no | Orden de presentación |
| paso | text |  | no | Paso del embudo bronze -> silver |
| tipo | text |  | no | filtro (deja pasar o descarta filas) o calculo (agrega filas calculadas) |
| filas | integer |  | no | Filas después del paso |
| variacion | integer |  | no | Filas del paso menos filas del paso anterior (negativo = descartadas) |
| en_embudo | boolean |  | no | Si el paso forma parte del embudo decreciente (filtros antes del primer cálculo) |
| descripcion | text |  | no | Descripción en lenguaje natural |

### ctl.rechazos

| columna | tipo | clave_primaria | admite_nulo | descripcion |
|---|---|---|---|---|
| id_rechazo | bigint | PK | no | Identificador del rechazo |
| id_carga | bigint |  | no | Identificador de la ejecución en ctl.log_cargas que escribió la fila |
| tabla_origen | text |  | no | Tabla de bronze de la que viene el registro rechazado |
| id_registro_origen | bigint |  | sí | Registro de bronze que se rechazó |
| regla | text |  | no | Regla de validación incumplida (nulo, rango, clave_duplicada, territorio_excluido, ...) |
| motivo | text |  | no | Motivo del rechazo en lenguaje natural |
| registro | jsonb |  | no | Registro original sin modificar (JSON) |
| fecha_rechazo | timestamp with time zone |  | no | Fecha y hora del rechazo |
