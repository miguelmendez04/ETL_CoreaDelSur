# ETL Corea del Sur: natalidad, envejecimiento y fuerza laboral

Proyecto ETL 2026 – Grupo 6. Maestría en IA y Ciencia de Datos, Universidad Autónoma de Occidente.

**Pregunta central:** ¿cómo impactará la disminución de la natalidad y el envejecimiento poblacional en la disponibilidad futura de la fuerza laboral en Corea del Sur?

## Arquitectura

Pipeline con arquitectura medallón sobre PostgreSQL:

| Capa | Contenido |
|---|---|
| **Bronze** | Datos crudos de cada fuente (KOSIS, World Bank, OECD, UN WPP) tal como llegan, solo inserción |
| **Silver** | Datos limpios, en formato largo, homologados y validados. Histórico y proyecciones en tablas separadas |
| **Gold** | Indicadores finales, escenarios de fuerza laboral y la capa de servicio del tablero (Power BI y web) |
| **ctl** | Bitácora de cargas (`ctl.log_cargas`) y registros rechazados con su motivo (`ctl.rechazos`) |

Documentación detallada en [`docs/`](docs/):

| Documento | Contenido |
|---|---|
| [01_diagnostico.md](docs/01_diagnostico.md) | Problema, hallazgos principales, perfilamiento de las fuentes y alcance |
| [02_diseno.md](docs/02_diseno.md) | Arquitectura, niveles de evidencia, grano, modelo estrella, escenarios e índice de riesgo (con diagramas) |
| [03_validacion.md](docs/03_validacion.md) | Reglas de validación, rechazos, embudo, KPIs, conciliación y pruebas |
| [fuentes_datos.md](docs/fuentes_datos.md) | Fuentes, tblId de KOSIS, indicadores WB, dataflows OCDE y fuente maestra por indicador |
| [linaje_datos.md](docs/linaje_datos.md) | Del archivo crudo al tablero, por registro y por indicador |
| [retroalimentacion_trazabilidad.md](docs/retroalimentacion_trazabilidad.md) | Cada comentario del profesor, el cambio hecho y dónde verificarlo |
| [diccionario_datos.md](docs/diccionario_datos.md) (y `.xlsx`) | Todas las tablas, columnas e indicadores, generado desde la base |

## Estructura

Cada capa del medallón existe en tres lugares: el código que la construye, sus tablas en PostgreSQL y sus archivos
en `data/`.

| Capa | Código | PostgreSQL | Archivos |
|---|---|---|---|
| Bronze | `src/extract/` + `src/load/bronze.py` | `bronze.*` | `data/bronze/<fuente>/<fecha>/`: crudo + `_metadata.json` |
| Silver | `src/transform/silver/` + `src/quality/validate.py` + `src/load/silver.py` | `silver.*`, `ctl.rechazos` | `data/silver/<fecha>/`: Parquet de cada tabla + rechazos + `manifest.json` |
| Gold | `src/transform/gold/` + `src/quality/kpis.py` + `src/load/gold.py` | `gold.*`, `gold.v_*`, `ctl.kpis` | `data/gold/<fecha>/`: tablas y vistas en Parquet y CSV + `manifest.json` |
| Control | `src/load/ctl.py` | `ctl.log_cargas` | `logs/pipeline.log` |

```
├── data/
│   ├── bronze/      crudo por fuente y fecha (solo KOSIS se versiona: es descarga manual)
│   ├── silver/      respaldo limpio en Parquet por fecha (no se versiona)
│   └── gold/        datos de negocio en Parquet y CSV por fecha (no se versiona)
├── src/
│   ├── extract/     bronze: un extractor por fuente + ejecutar.py
│   ├── transform/
│   │   ├── silver/  desde_bronze, normalize, homologacion, derive, reconcile, ejecutar
│   │   └── gold/    escenarios, riesgo, analisis, ejecutar
│   ├── load/        ctl (bitácora y COPY), bronze, silver, gold, archivos (respaldos en data/)
│   ├── quality/     validate (-> ctl.rechazos), kpis, diccionario, perfilamiento y lectura_bronze (notebooks)
│   └── utils/       configuración, logging y conexión
├── config/
│   ├── config.yaml  catálogo de fuentes y reglas de cada capa (bronze, silver, gold)
│   └── mappings/    dimensiones, etiquetas (inglés y coreano) y descripciones de tablas y columnas
├── sql/             DDL de los esquemas y vistas (Docker lo ejecuta al crear la base)
├── notebooks/       01-05 perfilamiento de calidad por fuente; 06 resultados de gold por pregunta de negocio
├── powerbi/         tablero de Power BI (.pbip: portada + 7 páginas, diseño del equipo); guía en powerbi/README.md
├── dashboard/       versión web del mismo tablero (un HTML con Plotly, sin conexión)
├── docs/            diagnóstico, diseño, validación, fuentes, linaje, retroalimentación y diccionario de datos
├── airflow/         orquestación con Apache Airflow: DAG etl_corea, imagen y guía (airflow/README.md)
├── tests/           pruebas de las tres capas
├── logs/            registro de ejecuciones
├── docker-compose.yml
└── main.py          ejecución manual: bronze -> silver -> gold (Airflow llama a las mismas funciones)
```

## Puesta en marcha

1. Crear el entorno e instalar dependencias:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copiar `.env.example` a `.env` y completar la contraseña de PostgreSQL y el token de UN WPP.
3. Levantar PostgreSQL (crea la base y los esquemas automáticamente con `sql/00_schemas.sql`):
   ```bash
   docker compose up -d
   ```
4. Ejecutar el pipeline completo (bronze -> silver -> gold, unos 3 minutos):
   ```bash
   python main.py
   ```
5. Revisar los resultados en la base, o abrir el tablero `powerbi/Tablero_ETL_Corea_Grupo6.pbip` y **Actualizar**
   (ver [powerbi/README.md](powerbi/README.md)):
   ```sql
   SELECT * FROM gold.v_kpis_calidad;
   SELECT * FROM gold.v_escenarios_resumen WHERE escenario_kostat = 'medio' AND anio IN (2030, 2050, 2072);
   ```
6. Opcional: regenerar la versión web del tablero y el diccionario de datos:
   ```bash
   python dashboard/generar_tablero.py      # dashboard/Tablero_ETL_Corea_Grupo6.html, se abre en cualquier navegador
   python -m src.quality.diccionario        # docs/diccionario_datos.md y .xlsx (lee el esquema real)
   ```

## Orquestación con Airflow

El pipeline se automatiza con **Apache Airflow 3** (opcional, en Docker). El DAG `etl_corea` extrae las cuatro
fuentes en paralelo, luego construye silver y gold, y al final verifica los KPIs de calidad. Corre cada semana o a
demanda, con reintentos automáticos y el log de cada tarea en la interfaz web.

```
bronze_worldbank ┐
bronze_oecd      ├─> silver ─> gold ─> verificar_kpis
bronze_unwpp     │
bronze_kosis     ┘
```

```bash
docker compose --profile airflow up -d --build    # interfaz en http://localhost:8080
```

Las tareas llaman a las mismas funciones que `python main.py`, así que el resultado y la bitácora en `ctl` son
idénticos. Puesta en marcha, conceptos y cómo diagnosticar fallos: [airflow/README.md](airflow/README.md).

## Extracción (capa bronze)

Todo lo que se extrae está declarado en `config/config.yaml`: para agregar un indicador de World Bank, un
dataflow de OECD o una tabla de KOSIS basta con añadirlo al catálogo, sin tocar código.

| Fuente | Método | Datasets | Tabla bronze |
|---|---|---|---|
| World Bank WDI | API v2 | 10 indicadores × 9 países | `bronze.worldbank_wdi` |
| OECD | API SDMX | productividad, fuerza laboral, participación por edad y sexo, fecundidad, dependencia (esta solo queda en bronze: la OCDE la mide como 65+/20-64, no comparable) | `bronze.oecd_sdmx` |
| UN WPP 2024 | Data Portal API (token) | población por edad y sexo | `bronze.unwpp_wpp2024` |
| KOSIS (KOSTAT) | descarga manual | 9 tablas (vitales, TFR, población, EAPS, proyecciones) | `bronze.kosis` |

```bash
python main.py --listar                          # catálogo de datasets
python main.py --capa bronze                     # solo extracción, todas las fuentes
python main.py --fuente oecd worldbank           # algunas fuentes
python main.py --dataset SP.POP.TOTL tfr_sido    # datasets puntuales
python main.py --sin-db                          # solo archivos crudos, sin PostgreSQL
python main.py --forzar                          # recargar aunque el crudo no haya cambiado
```

Por cada dataset el pipeline:

1. abre una carga en `ctl.log_cargas` (así también quedan registrados los fallos, con su mensaje);
2. extrae y guarda el crudo en `data/bronze/<fuente>/<AAAA-MM-DD>/`, sin sobrescribir nunca un archivo anterior;
3. inserta un registro por fila en `bronze.<tabla>` con su `id_carga` y `hash_registro`. Si el crudo es idéntico
   al de la última carga exitosa, no lo duplica y la carga queda `omitido`;
4. escribe `<archivo>_metadata.json` junto al crudo: URL, parámetros, sha256, cobertura detectada y avisos. Describe
   el archivo, no la carga (el mismo crudo da siempre el mismo metadata); la carga se busca en `ctl.log_cargas`
   por `archivo` o `hash_archivo`.

**KOSIS se descarga a mano** porque su OpenAPI está restringida a residentes de Corea. Para actualizarlo:
descargar la tabla desde [kosis.kr/eng](https://kosis.kr/eng/) en CSV, guardarla en
`data/bronze/kosis/<fecha de hoy>/` con el nombre del catálogo (`kosis.archivos` en `config.yaml`) y correr
`python main.py --fuente kosis`. El extractor toma la versión más reciente de cada archivo, verifica el encoding,
las columnas de dimensión y los años cubiertos, y avisa si falta algo.

**Dónde revisar una ejecución:** el resumen en consola y `logs/pipeline.log`; en la base,
`SELECT * FROM ctl.log_cargas ORDER BY id_carga DESC;`; y el `_metadata.json` de cada archivo crudo.

## Transformación (capa silver)

`python main.py --capa silver` reconstruye silver completo desde la última carga exitosa de cada dataset de
bronze, en una sola transacción (si algo falla, queda la versión anterior). Las reglas están en `config.yaml`
(sección `silver`) y en `config/mappings/`:

1. **Formato largo:** una fila por año × territorio × sexo × grupo de edad × indicador.
2. **Homologación** con diccionarios explícitos (`etiquetas.csv`), incluidas las etiquetas en coreano
   (`남자` -> `H`, `0 - 4세` -> `0-4`, `중위 추계` -> `medio`). Lo que no se reconoce va a `ctl.rechazos`.
3. **Unidades y frecuencia:** miles -> personas (EAPS); 85-89 … 100+ -> 85+; se descartan los agregados que se
   solapan. Las series mensuales de la EAPS entran como el promedio anual que publica KOSIS (los meses sueltos
   recientes quedan solo en bronze); la población es la de mitad de año.
4. **Validación:** nulos, tipo, rango por indicador, indicador válido, clave única y coherencia de totales
   (suma de edades ≈ total y H + M ≈ T en población y EAPS, con tolerancia de 0,5 % y el margen de redondeo de la
   fuente: la EAPS publica en miles). Cada rechazo queda en `ctl.rechazos` con su regla y motivo.
5. **Cálculos del pipeline:** agregados 0-14 / 15-64 / 65+, Chungnam + Sejong (tasas recalculadas desde los
   niveles), proporción de 65+, índice de envejecimiento y dependencia de vejez.
6. **Conciliación** maestra vs contraste (OECD, World Bank, UN WPP) en `silver.conciliacion`. La meta de ±3 % se
   mide en el histórico; en proyección la diferencia con UN WPP es esperable (otros supuestos de fecundidad y
   migración) y se guarda como contraste, no como error.

| Tabla | Contenido |
|---|---|
| `silver.fact_historico` | Observado 2000–2025: Corea (KOSIS/OECD, nacional + 17 si-do + Chungnam+Sejong) y países de comparación (World Bank) |
| `silver.fact_proyeccion` | KOSTAT sin modificar: nacional 2026–2072 (medio, fecundidad alta/baja y migración alta/baja/sin migración) y si-do 2026–2052 (medio) |
| `silver.conciliacion` | Diferencia % entre la fuente maestra y cada contraste |
| `silver.dim_*` | Territorio, edad, sexo e indicador (desde `config/mappings/`) |

Cada fila guarda `fuente`, `fecha_extraccion`, `version_publicacion`, `estado` (`preliminar`/`definitivo`),
`id_carga` (la carga silver) e `id_carga_origen` (la carga bronze de donde viene).

Los registros evaluados, válidos y rechazados de cada dataset de bronze quedan en `ctl.calidad_dataset` (vista
`gold.v_calidad_dataset`). Las filas que quedan después de cada paso (embudo bronze -> silver) se registran en
`ctl.pasos_silver` y se ven en
`gold.v_embudo_silver`.

Al terminar, cada tabla silver y los rechazos de esa ejecución quedan también en `data/silver/<fecha>/` (Parquet),
para analizarlos sin conectarse a la base.

## Capa gold

`python main.py --capa gold` calcula, desde silver:

| Tabla / vista | Pregunta | Contenido |
|---|---|---|
| `gold.escenario_fuerza_laboral` + `gold.supuestos` | 6b | Fuerza laboral potencial 2026–2072 por sexo y edad |
| `gold.escenarios_sensibilidad` | 6b | Fuerza laboral total con variantes de los parámetros de B, C y D |
| `gold.indicadores_riesgo` | 5 | Índice de riesgo demográfico por si-do (0–100) y ranking, con sus componentes |
| `gold.riesgo_sensibilidad` | 5 | Ranking de riesgo con otros pesos, normalización por percentiles y una variante de 6 componentes con z-score |
| `gold.asociaciones` | 7 | Correlaciones 2000–2025 en niveles y en variaciones anuales (asociación, no causalidad) |
| `gold.hitos_escasez` | 8 | Años en que se cruzan umbrales (pico de 15-64, relevo y reemplazo laboral < 100, dependencia ≥ 50 y ≥ 75), caída de la fuerza laboral y efecto de la migración en la población 15-64 |
| `ctl.kpis` / `gold.v_kpis_calidad` | — | KPIs de calidad del proyecto, una foto por ejecución |
| `gold.v_panel_indicadores` | 1, 3, 4, 9 | Un registro por año × territorio con todos los indicadores, incluidas defunciones, crecimiento natural y esperanza de vida (histórico + proyección media), con `tipo_dato` |
| `gold.v_natalidad_vs_15_64` | 2 | Nacimientos de cada año frente a quienes entran a 15-19 quince años después, y variación de 15-64 |
| `gold.v_senales_escasez` | 8 | Relevo generacional (15-19 por cada 100 de 60-64), reemplazo laboral (15-24 por cada 100 de 55-64), variación de 15-64 y dependencia, por año y si-do |
| `gold.v_proyeccion_escenarios` | 6a | Población 15-64 y 65+ y dependencia en los 8 escenarios de KOSTAT (fecundidad, migración y envejecimiento) |
| `gold.v_escenarios_resumen` | 6a, 6b | Fuerza laboral total por año, escenario KOSTAT y supuesto, junto a la población 15-64 |
| `gold.v_conciliacion` | — | Conciliación con nombres legibles y marca de tolerancia |

La pregunta 10 (información para política pública) se responde en el informe con las tres capas.

Todas las tablas y vistas gold se exportan además a `data/gold/<fecha>/` en Parquet y CSV, con un `manifest.json`
(filas, columnas, sha256 e `id_carga`): sirven para Power BI o Excel sin la base, y el notebook
`06_resultados_gold.ipynb` responde las preguntas de negocio directamente desde esos archivos.

**Tablero.** Al final de gold se escribe la capa de servicio del tablero, `data/gold/powerbi/pbi_*.parquet`
(`src/transform/gold/servicio_bi.py`): 16 tablas con la forma exacta que necesita cada visual. De ahí leen el
tablero de Power BI (`powerbi/Tablero_ETL_Corea_Grupo6.pbip`, diseño del equipo: portada y 7 páginas con menú
lateral) y su versión web (`python dashboard/generar_tablero.py`), que no necesita la base, Power BI ni internet.

**Escenarios propios** (parámetros en `config.yaml`, sección `gold`; son escenarios, no pronósticos).
Fuerza laboral = población proyectada KOSTAT × factor de cobertura × tasa de participación. El factor de cobertura
(población 15+ de la EAPS / población KOSTAT, por sexo y edad, en 2025) corrige que la EAPS no cubra militares ni
población institucional; con él, el año base reproduce la población activa observada.

- **A, participación constante:** cada tasa por sexo y grupo de edad queda en su valor de 2025.
- **B, tendencia 2015–2025:** se extrapola la tendencia lineal, con un cambio máximo de ±15 puntos, entre 0 y
  90 %, y congelada desde 2050.
- **C, convergencia OCDE:** cada tasa converge al promedio OCDE de su sexo y edad hasta 2050. Los grupos 15-19 y
  60+ quedan constantes porque la OCDE no publica edades equivalentes.
- **D, cierre de la brecha de género:** las mujeres cierran linealmente la mitad de su brecha de participación con
  los hombres hasta 2050; los hombres quedan como en A. Donde las mujeres ya participan más (15-29), su tasa no
  baja.

Los supuestos calculados (pendientes de la tendencia, objetivos OCDE, brechas de género) quedan guardados en `gold.supuestos`, y la
sensibilidad a sus parámetros en `gold.escenarios_sensibilidad`. El índice de riesgo por si-do usa cuatro
componentes con igual peso; `gold.riesgo_sensibilidad` muestra el ranking con otros esquemas de pesos y con
normalización por percentiles (Sejong, el único si-do cuya población de 15-64 crece, estira la escala min-max).
Las cifras regionales de la EAPS vienen de una encuesta por muestreo: se interpretan como tendencia.

## Supuestos del modelo (decisiones metodológicas)

Los escenarios y el índice de riesgo dependen de parámetros que **no vienen de ninguna fuente**: son decisiones
metodológicas del equipo. Todos están en `config.yaml` (sección `gold`), se guardan con cada ejecución en
`gold.supuestos` y su efecto se mide en las tablas de sensibilidad. Para cambiar uno se edita `config.yaml` y se
corre `python main.py --capa gold`. Cifras: fuerza laboral potencial, escenario KOSTAT medio, millones de personas.

| Parámetro | Valor | Por qué | Sensibilidad |
|---|---|---|---|
| Año base | 2025 | Último año observado de la EAPS | — |
| B: periodo de tendencia | 2015–2025 | Última década: refleja el aumento reciente de la participación femenina y de mayores | — |
| B: cambio máximo | ±15 puntos | Evita que una tendencia lineal lleve tasas a valores irreales en 50 años | 10 → 21,8 M en 2072; 15 → 22,8 M; 20 → 23,3 M |
| B: piso / tope | 0 % / 90 % | Límites físicos de una tasa de participación | — |
| B: congelar desde | 2050 | Las tendencias no siguen indefinidamente | 2040 → 22,2 M en 2072; 2060 → 22,8 M |
| C: año de convergencia | 2050 | Horizonte de una generación para cambios de comportamiento laboral | 2040 o 2060 → 19,7 M en 2072 (sin cambio: el alza femenina compensa la baja masculina) |
| C: equivalencia de edades | 20-29 = ½ 15-24 + ½ 25-54; 30-49 = 25-54; 50-59 = ½ 25-54 + ½ 55-64 | La OCDE publica 15-24, 25-54 y 55-64; la EAPS, grupos decenales | — |
| C: grupos constantes | 15-19 y 60+ | La OCDE no publica edades comparables | — |
| D: fracción de la brecha y año meta | ½ de la brecha, 2050 | Meta intermedia: cerrar toda la brecha en 25 años sería un cambio sin precedente | ¼ → 20,3 M en 2072; ½ → 21,0 M; completa → 22,3 M |
| Riesgo: componentes | Proporción 65+ y TFR (2025); variación de 15-64 y dependencia de vejez (2025 → 2052) | Situación actual y proyectada, dos de cada una | — |
| Riesgo: pesos | 25 % cada componente | Sin evidencia para priorizar uno | Gyeongsangbuk-do y Jeonbuk quedan en el top 5 en los 7 esquemas (pesos, percentiles y 6 componentes con z-score); Busan en 6 de 7 (7.º si solo se mira la proyección) |
| Señales de escasez | Dependencia de vejez ≥ 50 y ≥ 75 | Mitad y tres cuartos de la población en edad de trabajar | — |

Resultado base en 2072: A 19,6 M, B 22,8 M, C 19,6 M y D 21,0 M, frente a 29,6 M de población activa en 2025.
Con cualquier parámetro probado, la fuerza laboral potencial cae entre 21 % y 34 % a 2072.

La migración se analiza con los escenarios oficiales de KOSTAT, no con un supuesto propio: entre 2025 y 2050 la
población de 15-64 cae 28,5 % con migración alta, 31,9 % en el escenario medio, 35,2 % con migración baja y 36,8 %
sin migración. La migración amortigua la caída (unos 8 puntos entre los extremos), no la revierte.

## KPIs de calidad

Se calculan en cada ejecución desde `ctl` y silver (`ctl.kpis`, vista `gold.v_kpis_calidad`):

| KPI | Meta |
|---|---|
| Fuentes institucionales integradas | ≥ 3 |
| Indicadores con definición en el diccionario | 100 % |
| Contrastes del diccionario que coinciden con la conciliación | 100 % |
| Ejecuciones sin fallo técnico | ≥ 95 % |
| Registros válidos / rechazo, en cada carga silver | ≥ 98 % / ≤ 2 %, con el 100 % de rechazos con motivo |
| Completitud año × indicador | ≥ 95 % nacional, ≥ 90 % regional |
| Suma de los 17 si-do vs total nacional (±0,5 %) | 100 % de los años |
| Duplicados en bronze | se monitorean |
| Proyecciones con edición y escenario | 100 % |
| Pares maestra-contraste dentro de ±3 % (histórico) | ≥ 90 % |

## Pruebas

```bash
python -m pytest tests
```

Cubren la extracción (archivos, deduplicación, estructura de KOSIS), la homologación (incluidas las etiquetas
en coreano), las reglas de validación, los cálculos derivados, Chungnam + Sejong, los escenarios A/B/C/D, el
factor de cobertura, las asociaciones, el embudo, la calidad por dataset y el índice de riesgo con su sensibilidad
(35 pruebas).

## Equipo

Angie Tatiana Rodríguez Duque, Karin Stephany Parra Rosero, Maicol Andrés Narváez Rincón, Miguel Ángel Méndez Rodríguez.
