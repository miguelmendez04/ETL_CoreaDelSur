# ETL Corea del Sur: natalidad, envejecimiento y fuerza laboral

Proyecto ETL 2026 – Grupo 6. Maestría en IA y Ciencia de Datos, Universidad Autónoma de Occidente.

**Pregunta central:** ¿cómo impactará la disminución de la natalidad y el envejecimiento poblacional en la disponibilidad futura de la fuerza laboral en Corea del Sur?

## Arquitectura

Pipeline con arquitectura medallón sobre PostgreSQL:

| Capa | Contenido |
|---|---|
| **Bronze** | Datos crudos de cada fuente (KOSIS, World Bank, OECD, UN WPP) tal como llegan, solo inserción |
| **Silver** | Datos limpios, en formato largo, homologados y validados. Histórico y proyecciones en tablas separadas |
| **Gold** | Indicadores finales y escenarios de fuerza laboral para Power BI |
| **ctl** | Bitácora de cargas (`ctl.log_cargas`) y registros rechazados con su motivo (`ctl.rechazos`) |

## Estructura

```
├── data/            bronze/ silver/ gold/ (archivos locales, no se versionan)
├── src/
│   ├── extract/     un extractor por fuente + ejecutar.py (capa bronze)
│   ├── transform/   lectura de bronze, normalización, indicadores derivados, conciliación
│   ├── load/        escritura a PostgreSQL
│   ├── quality/     validaciones y KPIs de calidad
│   └── utils/       configuración, logging y conexión
├── config/
│   ├── config.yaml  parámetros y catálogo de fuentes (qué se extrae y cómo)
│   └── mappings/    dimensiones: territorios, edades, sexo, indicadores
├── sql/             DDL de los esquemas (Docker lo ejecuta al crear la base)
├── logs/            registro de ejecuciones
├── tests/           pruebas
├── notebooks/       perfilamiento de calidad por fuente y conciliación
├── docker-compose.yml
└── main.py          orquestación del pipeline
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
4. Ejecutar la extracción (capa bronze):
   ```bash
   python main.py
   ```

## Extracción (capa bronze)

Todo lo que se extrae está declarado en `config/config.yaml`: para agregar un indicador de World Bank, un
dataflow de OECD o una tabla de KOSIS basta con añadirlo al catálogo, sin tocar código.

| Fuente | Método | Datasets | Tabla bronze |
|---|---|---|---|
| World Bank WDI | API v2 | 10 indicadores × 9 países | `bronze.worldbank_wdi` |
| OECD | API SDMX | productividad, fuerza laboral, fecundidad, dependencia | `bronze.oecd_sdmx` |
| UN WPP 2024 | Data Portal API (token) | población por edad y sexo | `bronze.unwpp_wpp2024` |
| KOSIS (KOSTAT) | descarga manual | 9 tablas (vitales, TFR, población, EAPS, proyecciones) | `bronze.kosis` |

```bash
python main.py --listar                          # catálogo de datasets
python main.py                                   # todas las fuentes
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
4. escribe `<archivo>_metadata.json` junto al crudo: URL, parámetros, sha256, cobertura detectada, avisos e `id_carga`.

**KOSIS se descarga a mano** porque su OpenAPI está restringida a residentes de Corea. Para actualizarlo:
descargar la tabla desde [kosis.kr/eng](https://kosis.kr/eng/) en CSV, guardarla en
`data/bronze/kosis/<fecha de hoy>/` con el nombre del catálogo (`kosis.archivos` en `config.yaml`) y correr
`python main.py --fuente kosis`. El extractor toma la versión más reciente de cada archivo, verifica el encoding,
las columnas de dimensión y los años cubiertos, y avisa si falta algo.

**Dónde revisar una ejecución:** el resumen en consola y `logs/pipeline.log`; en la base,
`SELECT * FROM ctl.log_cargas ORDER BY id_carga DESC;`; y el `_metadata.json` de cada archivo crudo.

## Equipo

Angie Tatiana Rodríguez Duque, Karin Stephany Parra Rosero, Maicol Andrés Narváez Rincón, Miguel Ángel Méndez Rodríguez.
