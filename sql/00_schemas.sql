-- =====================================================================
-- Proyecto ETL 2026 - Grupo 6 - Corea del Sur
-- Esquemas y tablas de la arquitectura medallón (bronze / silver / gold / ctl)
-- Ejecutar sobre una base vacía:  psql -d etl_corea -f sql/00_schemas.sql
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS ctl;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ---------------------------------------------------------------------
-- CONTROL
-- ---------------------------------------------------------------------

-- Una fila por ejecución. Cada ejecución genera un id_carga nuevo.
CREATE TABLE IF NOT EXISTS ctl.log_cargas (
    id_carga          BIGSERIAL PRIMARY KEY,
    capa              TEXT        NOT NULL CHECK (capa IN ('bronze', 'silver', 'gold')),
    fuente            TEXT        NOT NULL,
    dataset           TEXT        NOT NULL,
    parametros        JSONB,
    inicio            TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin               TIMESTAMPTZ,
    estado            TEXT        NOT NULL DEFAULT 'en_curso'
                                  CHECK (estado IN ('en_curso', 'exito', 'fallo')),
    filas_extraidas   INTEGER,
    filas_validas     INTEGER,
    filas_rechazadas  INTEGER,
    mensaje_error     TEXT
);

-- Registros que no pasan las validaciones bronze -> silver, con su motivo.
CREATE TABLE IF NOT EXISTS ctl.rechazos (
    id_rechazo        BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    tabla_origen      TEXT        NOT NULL,
    id_registro_origen BIGINT,
    regla             TEXT        NOT NULL,  -- p. ej. 'rango', 'nulo', 'clave_duplicada', 'territorio_invalido'
    motivo            TEXT        NOT NULL,
    registro          JSONB       NOT NULL,
    fecha_rechazo     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rechazos_carga ON ctl.rechazos (id_carga);

-- ---------------------------------------------------------------------
-- BRONZE: respuesta cruda de cada API, solo inserción (append-only).
-- Una fila por registro de la respuesta; el registro original va en JSONB.
-- hash_registro permite monitorear duplicados entre cargas.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bronze.kosis_openapi (
    id_bronze         BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    fuente            TEXT        NOT NULL DEFAULT 'KOSIS',
    dataset           TEXT        NOT NULL,          -- clave del dataset en sources.yaml
    org_id            TEXT,
    tbl_id            TEXT,
    url               TEXT        NOT NULL,
    params            JSONB,                         -- sin la API key
    fecha_extraccion  TIMESTAMPTZ NOT NULL,
    registro          JSONB       NOT NULL,
    hash_registro     TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.worldbank_wdi (
    id_bronze         BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    fuente            TEXT        NOT NULL DEFAULT 'WB',
    dataset           TEXT        NOT NULL,          -- código del indicador WDI
    url               TEXT        NOT NULL,
    params            JSONB,
    fecha_extraccion  TIMESTAMPTZ NOT NULL,
    registro          JSONB       NOT NULL,
    hash_registro     TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.oecd_sdmx (
    id_bronze         BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    fuente            TEXT        NOT NULL DEFAULT 'OECD',
    dataset           TEXT        NOT NULL,          -- dataflow SDMX
    url               TEXT        NOT NULL,
    params            JSONB,
    fecha_extraccion  TIMESTAMPTZ NOT NULL,
    registro          JSONB       NOT NULL,
    hash_registro     TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.unwpp_wpp2024 (
    id_bronze         BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    fuente            TEXT        NOT NULL DEFAULT 'UNWPP',
    dataset           TEXT        NOT NULL,          -- nombre del archivo CSV
    url               TEXT        NOT NULL,
    params            JSONB,
    fecha_extraccion  TIMESTAMPTZ NOT NULL,
    registro          JSONB       NOT NULL,
    hash_registro     TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_kosis_hash  ON bronze.kosis_openapi (hash_registro);
CREATE INDEX IF NOT EXISTS ix_wb_hash     ON bronze.worldbank_wdi (hash_registro);
CREATE INDEX IF NOT EXISTS ix_oecd_hash   ON bronze.oecd_sdmx     (hash_registro);
CREATE INDEX IF NOT EXISTS ix_unwpp_hash  ON bronze.unwpp_wpp2024 (hash_registro);

-- ---------------------------------------------------------------------
-- SILVER: dimensiones (se cargan desde config/mappings/*.csv)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.dim_territorio (
    cod_territorio    TEXT PRIMARY KEY,
    nombre_es         TEXT NOT NULL,
    nombre_en         TEXT,
    nombre_ko         TEXT,
    tipo              TEXT NOT NULL CHECK (tipo IN ('nacional', 'sido', 'agregado', 'pais', 'agregado_int')),
    cod_kosis         TEXT,
    cod_kosis_alt     TEXT,        -- código nuevo tras cambio de nombre (Gangwon, Jeonbuk)
    iso3              TEXT,
    vigente_desde     SMALLINT,
    vigente_hasta     SMALLINT,
    observacion       TEXT
);

CREATE TABLE IF NOT EXISTS silver.dim_edad (
    cod_grupo_edad    TEXT PRIMARY KEY,
    edad_min          SMALLINT NOT NULL,
    edad_max          SMALLINT,    -- NULL = abierto (85+, 65+, TOTAL)
    tipo              TEXT NOT NULL CHECK (tipo IN ('total', 'quinquenal', 'agregado')),
    orden             SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.dim_sexo (
    cod_sexo          TEXT PRIMARY KEY CHECK (cod_sexo IN ('T', 'H', 'M')),
    nombre            TEXT NOT NULL,
    cod_kosis         TEXT,
    cod_worldbank     TEXT,
    cod_oecd          TEXT
);

CREATE TABLE IF NOT EXISTS silver.dim_indicador (
    cod_indicador       TEXT PRIMARY KEY,
    nombre              TEXT NOT NULL,
    definicion          TEXT NOT NULL,
    unidad              TEXT NOT NULL,
    frecuencia_original TEXT NOT NULL CHECK (frecuencia_original IN ('anual', 'trimestral', 'mensual')),
    fuente_maestra      TEXT NOT NULL,
    fuente_contraste    TEXT,
    es_derivado         BOOLEAN NOT NULL DEFAULT false,
    rango_min           NUMERIC,
    rango_max           NUMERIC
);

-- ---------------------------------------------------------------------
-- SILVER: hechos. Histórico y proyecciones SIEMPRE en tablas separadas.
-- ---------------------------------------------------------------------

-- Histórico observado 2000-2025 (fuente maestra + indicadores derivados).
CREATE TABLE IF NOT EXISTS silver.fact_historico (
    anio                SMALLINT NOT NULL CHECK (anio BETWEEN 1990 AND 2100),
    cod_territorio      TEXT     NOT NULL REFERENCES silver.dim_territorio (cod_territorio),
    sexo                TEXT     NOT NULL REFERENCES silver.dim_sexo (cod_sexo),
    grupo_edad          TEXT     NOT NULL REFERENCES silver.dim_edad (cod_grupo_edad),
    cod_indicador       TEXT     NOT NULL REFERENCES silver.dim_indicador (cod_indicador),
    valor               NUMERIC  NOT NULL,
    fuente              TEXT     NOT NULL,
    fecha_extraccion    TIMESTAMPTZ NOT NULL,
    version_publicacion TEXT,
    estado              TEXT     NOT NULL CHECK (estado IN ('preliminar', 'definitivo')),
    id_carga            BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (anio, cod_territorio, sexo, grupo_edad, cod_indicador)
);

-- Proyecciones oficiales KOSTAT, sin modificar.
CREATE TABLE IF NOT EXISTS silver.fact_proyeccion (
    anio                SMALLINT NOT NULL CHECK (anio BETWEEN 2000 AND 2100),
    cod_territorio      TEXT     NOT NULL REFERENCES silver.dim_territorio (cod_territorio),
    sexo                TEXT     NOT NULL REFERENCES silver.dim_sexo (cod_sexo),
    grupo_edad          TEXT     NOT NULL REFERENCES silver.dim_edad (cod_grupo_edad),
    cod_indicador       TEXT     NOT NULL REFERENCES silver.dim_indicador (cod_indicador),
    edicion_proyeccion  TEXT     NOT NULL,   -- p. ej. 'KOSTAT_2022_2072'
    escenario           TEXT     NOT NULL CHECK (escenario IN ('medio', 'alto', 'bajo')),
    valor               NUMERIC  NOT NULL,
    fuente              TEXT     NOT NULL,
    fecha_extraccion    TIMESTAMPTZ NOT NULL,
    version_publicacion TEXT,
    estado              TEXT     NOT NULL CHECK (estado IN ('preliminar', 'definitivo')),
    id_carga            BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (anio, cod_territorio, sexo, grupo_edad, cod_indicador, edicion_proyeccion, escenario)
);

-- Maestra vs contraste. El contraste nunca reemplaza el valor maestro.
-- nivel = 'historico' | 'proyeccion'. En histórico, escenario = 'NA'.
CREATE TABLE IF NOT EXISTS silver.conciliacion (
    nivel               TEXT     NOT NULL CHECK (nivel IN ('historico', 'proyeccion')),
    anio                SMALLINT NOT NULL,
    cod_territorio      TEXT     NOT NULL REFERENCES silver.dim_territorio (cod_territorio),
    sexo                TEXT     NOT NULL REFERENCES silver.dim_sexo (cod_sexo),
    grupo_edad          TEXT     NOT NULL REFERENCES silver.dim_edad (cod_grupo_edad),
    cod_indicador       TEXT     NOT NULL REFERENCES silver.dim_indicador (cod_indicador),
    escenario           TEXT     NOT NULL DEFAULT 'NA',
    fuente_maestra      TEXT     NOT NULL,
    fuente_contraste    TEXT     NOT NULL,
    valor_maestra       NUMERIC  NOT NULL,
    valor_contraste     NUMERIC  NOT NULL,
    dif_abs             NUMERIC  GENERATED ALWAYS AS (valor_contraste - valor_maestra) STORED,
    dif_pct             NUMERIC  GENERATED ALWAYS AS (
                            CASE WHEN valor_maestra = 0 THEN NULL
                                 ELSE (valor_contraste - valor_maestra) / abs(valor_maestra) * 100 END
                        ) STORED,
    id_carga            BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (nivel, anio, cod_territorio, sexo, grupo_edad, cod_indicador, escenario, fuente_contraste)
);

-- ---------------------------------------------------------------------
-- GOLD: se construye en el siguiente avance (indicadores_riesgo,
-- escenario_fuerza_laboral con id_supuesto y version_modelo, vistas Power BI).
-- ---------------------------------------------------------------------
