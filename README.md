# ETL Corea del Sur: natalidad, envejecimiento y fuerza laboral

Proyecto ETL 2026 – Grupo 6. Maestría en IA y Ciencia de Datos, Universidad Autónoma de Occidente.

**Pregunta central:** ¿cómo impactará la disminución de la natalidad y el envejecimiento poblacional en la disponibilidad futura de la fuerza laboral en Corea del Sur?

## Arquitectura

Pipeline con arquitectura medallón sobre PostgreSQL:

| Capa | Contenido |
|---|---|
| **Bronze** | Respuestas crudas de las APIs (KOSIS, World Bank, OECD, UN WPP), solo inserción |
| **Silver** | Datos limpios, en formato largo, homologados y validados. Histórico y proyecciones en tablas separadas |
| **Gold** | Indicadores finales y escenarios de fuerza laboral para Power BI |
| **ctl** | Bitácora de cargas y registros rechazados con su motivo |

## Estructura

```
├── data/            bronze/ silver/ gold/ (archivos locales, no se versionan)
├── src/
│   ├── extract/     un extractor por fuente
│   ├── transform/   normalización, indicadores derivados, conciliación
│   ├── load/        escritura a PostgreSQL
│   ├── quality/     validaciones y KPIs de calidad
│   └── utils/       funciones comunes
├── config/
│   ├── config.yaml  parámetros y catálogo de fuentes
│   └── mappings/    dimensiones: territorios, edades, sexo, indicadores
├── sql/             DDL de los esquemas
├── logs/            registro de ejecuciones
├── tests/           pruebas
├── notebooks/       análisis exploratorio
└── main.py          orquestación del pipeline
```

## Puesta en marcha

1. Crear el entorno e instalar dependencias:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copiar `.env.example` a `.env` y completar la API key de KOSIS y los datos de PostgreSQL.
3. Crear los esquemas en la base:
   ```bash
   psql -d etl_corea -f sql/00_schemas.sql
   ```
4. Ejecutar el pipeline:
   ```bash
   python main.py
   ```

## Equipo

Angie Tatiana Rodríguez Duque, Karin Stephany Parra Rosero, Maicol Andrés Narváez Rincón, Miguel Ángel Méndez Rodríguez.
