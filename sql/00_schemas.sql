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

-- Una fila por ejecución y dataset. Cada ejecución genera un id_carga nuevo.
-- estado 'omitido' = el archivo crudo es idéntico (mismo hash) al de la última carga exitosa: no se duplica en bronze.
CREATE TABLE IF NOT EXISTS ctl.log_cargas (
    id_carga          BIGSERIAL PRIMARY KEY,
    capa              TEXT        NOT NULL CHECK (capa IN ('bronze', 'silver', 'gold')),
    fuente            TEXT        NOT NULL,
    dataset           TEXT        NOT NULL,
    parametros        JSONB,
    inicio            TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin               TIMESTAMPTZ,
    estado            TEXT        NOT NULL DEFAULT 'en_curso'
                                  CHECK (estado IN ('en_curso', 'exito', 'fallo', 'omitido')),
    metodo            TEXT        CHECK (metodo IN ('api', 'descarga_manual', 'pipeline')),
    archivo           TEXT,                          -- archivo crudo en data/bronze/<fuente>/<fecha>/
    hash_archivo      TEXT,                          -- sha256 del contenido crudo
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

-- Filas después de cada paso de bronze -> silver (embudo): 'filtro' deja pasar o descarta, 'calculo' agrega filas
-- calculadas en el pipeline. id_carga = la carga de silver.fact_historico de esa ejecución.
CREATE TABLE IF NOT EXISTS ctl.pasos_silver (
    id_carga     BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    orden        SMALLINT NOT NULL,
    paso         TEXT     NOT NULL,
    tipo         TEXT     NOT NULL CHECK (tipo IN ('filtro', 'calculo')),
    filas        INTEGER  NOT NULL,
    variacion    INTEGER  NOT NULL,  -- filas - filas del paso anterior (negativo = descartadas)
    en_embudo    BOOLEAN  NOT NULL,  -- filtros antes del primer cálculo: forman el embudo decreciente
    descripcion  TEXT     NOT NULL,
    PRIMARY KEY (id_carga, orden)
);
CREATE INDEX IF NOT EXISTS ix_log_dataset ON ctl.log_cargas (capa, fuente, dataset, estado);

-- ---------------------------------------------------------------------
-- BRONZE: datos crudos de cada fuente, solo inserción (append-only).
-- Una fila por registro de la respuesta (o por fila del CSV); el registro original va en JSONB, sin modificar.
-- hash_registro permite monitorear duplicados entre cargas. El archivo crudo de origen está en ctl.log_cargas.
-- ---------------------------------------------------------------------

-- KOSIS: descarga manual de CSV (la OpenAPI está restringida a residentes de Corea).
-- Cada fila del CSV es un registro; las claves del JSONB son los encabezados del archivo
-- (en archivos con encabezado doble: "periodo | ítem").
CREATE TABLE IF NOT EXISTS bronze.kosis (
    id_bronze         BIGSERIAL PRIMARY KEY,
    id_carga          BIGINT      NOT NULL REFERENCES ctl.log_cargas (id_carga),
    fuente            TEXT        NOT NULL DEFAULT 'KOSIS',
    dataset           TEXT        NOT NULL,          -- clave en config.yaml (kosis.archivos)
    org_id            TEXT,
    tbl_id            TEXT,
    url               TEXT        NOT NULL,          -- tabla en kosis.kr
    params            JSONB,                         -- archivo, encoding, formato
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
    dataset           TEXT        NOT NULL,          -- clave en config.yaml (oecd.datasets); el dataflow va en params
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
    dataset           TEXT        NOT NULL,          -- clave en config.yaml (unwpp.datasets)
    url               TEXT        NOT NULL,
    params            JSONB,
    fecha_extraccion  TIMESTAMPTZ NOT NULL,
    registro          JSONB       NOT NULL,
    hash_registro     TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_kosis_hash  ON bronze.kosis         (hash_registro);
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
    tipo              TEXT NOT NULL CHECK (tipo IN ('total', 'quinquenal', 'decenal', 'agregado')),  -- decenal: grupos de la EAPS
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
    id_carga            BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),  -- carga silver que escribió la fila
    id_carga_origen     BIGINT   REFERENCES ctl.log_cargas (id_carga),           -- carga bronze de donde viene (NULL si es derivado)
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
    id_carga            BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),  -- carga silver que escribió la fila
    id_carga_origen     BIGINT   REFERENCES ctl.log_cargas (id_carga),           -- carga bronze de donde viene (NULL si es derivado)
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
-- GOLD: indicadores finales y escenarios propios, listos para Power BI.
-- Las tablas las calcula el pipeline (python main.py --capa gold); las vistas leen silver y gold.
-- ---------------------------------------------------------------------

-- Supuestos de cada escenario propio (A/B/C), versionados.
CREATE TABLE IF NOT EXISTS gold.supuestos (
    id_supuesto       TEXT     NOT NULL,          -- A | B | C
    version_modelo    TEXT     NOT NULL,
    nombre            TEXT     NOT NULL,
    descripcion       TEXT     NOT NULL,
    parametros        JSONB    NOT NULL,
    id_carga          BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (id_supuesto, version_modelo)
);

-- Pregunta 6b: fuerza laboral potencial = población proyectada oficial × tasa de participación supuesta.
-- Es un ESCENARIO del equipo, no un pronóstico.
CREATE TABLE IF NOT EXISTS gold.escenario_fuerza_laboral (
    anio               SMALLINT NOT NULL,
    escenario_kostat   TEXT     NOT NULL CHECK (escenario_kostat IN ('medio', 'alto', 'bajo')),
    id_supuesto        TEXT     NOT NULL,
    version_modelo     TEXT     NOT NULL,
    sexo               TEXT     NOT NULL REFERENCES silver.dim_sexo (cod_sexo),
    grupo_edad         TEXT     NOT NULL REFERENCES silver.dim_edad (cod_grupo_edad),
    poblacion          NUMERIC  NOT NULL,         -- KOSTAT, edición KOSTAT_2022_2072
    factor_cobertura   NUMERIC  NOT NULL,         -- pob 15+ EAPS / pob KOSTAT en el año base (población civil)
    tasa_participacion NUMERIC  NOT NULL,         -- % supuesto para ese año
    fuerza_laboral     NUMERIC  NOT NULL,         -- personas
    id_carga           BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (anio, escenario_kostat, id_supuesto, version_modelo, sexo, grupo_edad),
    FOREIGN KEY (id_supuesto, version_modelo) REFERENCES gold.supuestos (id_supuesto, version_modelo)
);

-- Pregunta 5: si-do con mayor riesgo demográfico. Índice descriptivo (no causal) con pesos en config.yaml.
CREATE TABLE IF NOT EXISTS gold.indicadores_riesgo (
    cod_territorio            TEXT     PRIMARY KEY REFERENCES silver.dim_territorio (cod_territorio),
    anio_base                 SMALLINT NOT NULL,
    anio_proyeccion           SMALLINT NOT NULL,
    prop_65mas                NUMERIC,
    tfr                       NUMERIC,
    dependencia_vejez         NUMERIC,
    indice_envejecimiento     NUMERIC,
    tasa_participacion        NUMERIC,
    var_pob_15_64_hist_pct    NUMERIC,      -- cambio 2015 -> año base
    var_pob_15_64_proy_pct    NUMERIC,      -- cambio año base -> año proyección (KOSTAT, escenario medio)
    dependencia_vejez_proy    NUMERIC,
    indice_riesgo             NUMERIC  NOT NULL,   -- 0 (menor) a 100 (mayor)
    ranking                   SMALLINT NOT NULL,
    id_carga                  BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga)
);

-- KPIs de calidad (CLAUDE.md, sección 7): una foto por ejecución para ver su evolución.
CREATE TABLE IF NOT EXISTS ctl.kpis (
    id_carga   BIGINT  NOT NULL REFERENCES ctl.log_cargas (id_carga),
    kpi        TEXT    NOT NULL,
    valor      NUMERIC,
    meta       TEXT    NOT NULL,
    cumple     BOOLEAN NOT NULL,
    detalle    TEXT,
    PRIMARY KEY (id_carga, kpi)
);

-- Vistas para Power BI --------------------------------------------------

-- Panel anual por territorio: histórico + proyección oficial (escenario medio), una columna por indicador.
CREATE OR REPLACE VIEW gold.v_panel_indicadores AS
WITH base AS (
    SELECT 'historico' AS nivel, 'observado' AS escenario, anio, cod_territorio, cod_indicador, sexo, grupo_edad, valor, estado
    FROM silver.fact_historico
    UNION ALL
    SELECT 'proyeccion', escenario, anio, cod_territorio, cod_indicador, sexo, grupo_edad, valor, estado
    FROM silver.fact_proyeccion WHERE escenario = 'medio'
)
SELECT b.nivel, b.escenario, b.anio, b.cod_territorio, t.nombre_es AS territorio, t.tipo AS tipo_territorio,
       max(valor) FILTER (WHERE cod_indicador = 'TFR' AND grupo_edad = 'TOTAL')                  AS tfr,
       max(valor) FILTER (WHERE cod_indicador = 'NACIMIENTOS' AND grupo_edad = 'TOTAL')          AS nacimientos,
       max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = 'TOTAL')            AS poblacion_total,
       max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '0-14')             AS pob_0_14,
       max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '15-64')            AS pob_15_64,
       max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '65+')              AS pob_65mas,
       max(valor) FILTER (WHERE cod_indicador = 'PROP_65MAS' AND grupo_edad = 'TOTAL')           AS prop_65mas,
       max(valor) FILTER (WHERE cod_indicador = 'INDICE_ENVEJECIMIENTO' AND grupo_edad = 'TOTAL')AS indice_envejecimiento,
       max(valor) FILTER (WHERE cod_indicador = 'DEPENDENCIA_VEJEZ' AND grupo_edad = 'TOTAL')    AS dependencia_vejez,
       max(valor) FILTER (WHERE cod_indicador = 'POB_ACTIVA' AND grupo_edad = '15+')             AS pob_activa,
       max(valor) FILTER (WHERE cod_indicador = 'OCUPADOS' AND grupo_edad = '15+')               AS ocupados,
       max(valor) FILTER (WHERE cod_indicador = 'TASA_PARTICIPACION' AND grupo_edad = '15+')     AS tasa_participacion,
       max(valor) FILTER (WHERE cod_indicador = 'TASA_DESEMPLEO' AND grupo_edad = '15+')         AS tasa_desempleo,
       max(valor) FILTER (WHERE cod_indicador = 'PIB_HORA' AND grupo_edad = 'TOTAL')             AS pib_hora,
       max(valor) FILTER (WHERE cod_indicador = 'PIB_OCUPADO' AND grupo_edad = 'TOTAL')          AS pib_ocupado,
       bool_or(estado = 'preliminar')                                                   AS tiene_preliminares
FROM base b JOIN silver.dim_territorio t USING (cod_territorio)
WHERE b.sexo = 'T' AND b.grupo_edad IN ('TOTAL', '0-14', '15-64', '65+', '15+')
GROUP BY b.nivel, b.escenario, b.anio, b.cod_territorio, t.nombre_es, t.tipo;

-- Escenarios de fuerza laboral agregados (total país) junto a la población 15-64 proyectada.
CREATE OR REPLACE VIEW gold.v_escenarios_resumen AS
SELECT e.anio, e.escenario_kostat, e.id_supuesto, s.nombre AS supuesto, e.version_modelo,
       sum(e.fuerza_laboral) AS fuerza_laboral, sum(e.poblacion) AS poblacion_15mas,
       sum(e.fuerza_laboral) / sum(e.poblacion) * 100 AS tasa_participacion_agregada,
       p.valor AS pob_15_64
FROM gold.escenario_fuerza_laboral e
JOIN gold.supuestos s USING (id_supuesto, version_modelo)
LEFT JOIN silver.fact_proyeccion p ON p.anio = e.anio AND p.escenario = e.escenario_kostat AND p.cod_territorio = '00'
     AND p.sexo = 'T' AND p.grupo_edad = '15-64' AND p.cod_indicador = 'POBLACION' AND p.edicion_proyeccion = 'KOSTAT_2022_2072'
GROUP BY e.anio, e.escenario_kostat, e.id_supuesto, s.nombre, e.version_modelo, p.valor;

-- Conciliación con nombres legibles y marca de tolerancia.
CREATE OR REPLACE VIEW gold.v_conciliacion AS
SELECT c.*, i.nombre AS indicador, abs(c.dif_pct) <= 3 AS dentro_tolerancia
FROM silver.conciliacion c JOIN silver.dim_indicador i USING (cod_indicador);

-- Última foto de los KPIs de calidad.
CREATE OR REPLACE VIEW gold.v_kpis_calidad AS
SELECT k.* FROM ctl.kpis k WHERE k.id_carga = (SELECT max(id_carga) FROM ctl.kpis);

-- Embudo de la última ejecución de silver (pasos y filas), para Power BI.
CREATE OR REPLACE VIEW gold.v_embudo_silver AS
SELECT p.* FROM ctl.pasos_silver p WHERE p.id_carga = (SELECT max(id_carga) FROM ctl.pasos_silver);

-- Dimensión de años para Power BI: une en un mismo eje el histórico (panel) y el futuro (escenarios).
CREATE OR REPLACE VIEW gold.v_anios AS
SELECT DISTINCT anio FROM silver.fact_historico UNION SELECT DISTINCT anio FROM silver.fact_proyeccion;

-- Dimensión de territorio para Power BI: filtra a la vez el panel, el riesgo y las señales por si-do.
CREATE OR REPLACE VIEW gold.v_territorios AS
SELECT cod_territorio, nombre_es AS territorio, nombre_en, tipo, iso3,
       CASE tipo WHEN 'nacional' THEN 1 WHEN 'sido' THEN 2 WHEN 'agregado' THEN 3 WHEN 'agregado_int' THEN 4 ELSE 5 END AS orden_tipo
FROM silver.dim_territorio;

-- Pregunta 7: asociación (no causalidad) entre envejecimiento, empleo y productividad, Corea 2000-2025.
CREATE TABLE IF NOT EXISTS gold.asociaciones (
    variable_x        TEXT     NOT NULL,
    variable_y        TEXT     NOT NULL,
    anio_inicio       SMALLINT NOT NULL,
    anio_fin          SMALLINT NOT NULL,
    n                 SMALLINT NOT NULL,
    corr_niveles      NUMERIC,           -- Pearson en niveles (las series con tendencia suelen correlacionar)
    corr_variaciones  NUMERIC,           -- Pearson en variaciones anuales (¿se mueven juntas año a año?)
    id_carga          BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (variable_x, variable_y)
);

-- Pregunta 8: hitos de escasez laboral (umbrales que se cruzan y caída de la fuerza laboral por escenario).
CREATE TABLE IF NOT EXISTS gold.hitos_escasez (
    hito               TEXT     NOT NULL,
    escenario_kostat   TEXT     NOT NULL,
    id_supuesto        TEXT     NOT NULL DEFAULT '-',   -- '-' si el hito no depende de un supuesto propio
    anio               SMALLINT,                        -- NULL: el umbral no se cruza en el horizonte
    valor              NUMERIC,
    descripcion        TEXT     NOT NULL,
    id_carga           BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (hito, escenario_kostat, id_supuesto)
);

-- Sensibilidad del ranking de riesgo a los pesos del índice.
CREATE TABLE IF NOT EXISTS gold.riesgo_sensibilidad (
    cod_territorio  TEXT     NOT NULL,
    esquema         TEXT     NOT NULL,
    indice_riesgo   NUMERIC  NOT NULL,
    ranking         SMALLINT NOT NULL,
    id_carga        BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (cod_territorio, esquema)
);

-- Sensibilidad de los escenarios B y C a sus parámetros (escenario KOSTAT medio, total país).
CREATE TABLE IF NOT EXISTS gold.escenarios_sensibilidad (
    id_supuesto     TEXT     NOT NULL,
    variante        TEXT     NOT NULL,
    anio            SMALLINT NOT NULL,
    fuerza_laboral  NUMERIC  NOT NULL,
    id_carga        BIGINT   NOT NULL REFERENCES ctl.log_cargas (id_carga),
    PRIMARY KEY (id_supuesto, variante, anio)
);

-- Pregunta 2: natalidad y población en edad de trabajar. Los nacidos en t entran a la edad de trabajar en t+15:
-- la caída de nacimientos 2000-2025 ya está "escrita" en los ingresos a 15-19 hasta 2040.
CREATE OR REPLACE VIEW gold.v_natalidad_vs_15_64 AS
WITH pob AS (
    SELECT anio, grupo_edad, valor, 'historico' AS nivel FROM silver.fact_historico
    WHERE cod_territorio = '00' AND sexo = 'T' AND cod_indicador = 'POBLACION' AND grupo_edad IN ('15-19', '15-64')
    UNION ALL
    SELECT anio, grupo_edad, valor, 'proyeccion' FROM silver.fact_proyeccion
    WHERE cod_territorio = '00' AND sexo = 'T' AND cod_indicador = 'POBLACION' AND grupo_edad IN ('15-19', '15-64')
      AND escenario = 'medio' AND edicion_proyeccion = 'KOSTAT_2022_2072'
), anual AS (
    SELECT anio, nivel, max(valor) FILTER (WHERE grupo_edad = '15-19') AS pob_15_19,
           max(valor) FILTER (WHERE grupo_edad = '15-64') AS pob_15_64
    FROM pob GROUP BY anio, nivel
), nac AS (
    SELECT anio, valor AS nacimientos FROM silver.fact_historico
    WHERE cod_territorio = '00' AND sexo = 'T' AND cod_indicador = 'NACIMIENTOS'
)
SELECT a.anio, a.nivel, n.nacimientos, a.pob_15_19, a.pob_15_64,
       (a.pob_15_64 / lag(a.pob_15_64) OVER (ORDER BY a.anio) - 1) * 100       AS var_pob_15_64_pct,
       n15.nacimientos                                                          AS nacidos_hace_15,
       c.nacidos_cohorte_15_19,                                                 -- nacidos en t-19 ... t-15
       a.pob_15_19 / c.nacidos_cohorte_15_19 * 100                              AS pct_cohorte_presente
FROM anual a
LEFT JOIN nac n   ON n.anio = a.anio
LEFT JOIN nac n15 ON n15.anio = a.anio - 15
LEFT JOIN LATERAL (
    SELECT sum(nacimientos) AS nacidos_cohorte_15_19 FROM nac
    WHERE nac.anio BETWEEN a.anio - 19 AND a.anio - 15 HAVING count(*) = 5
) c ON true;

-- Pregunta 8: señales tempranas de escasez laboral por año y territorio (histórico + proyección media).
CREATE OR REPLACE VIEW gold.v_senales_escasez AS
WITH base AS (
    SELECT 'historico' AS nivel, anio, cod_territorio, cod_indicador, grupo_edad, valor
    FROM silver.fact_historico WHERE sexo = 'T'
    UNION ALL
    SELECT 'proyeccion', anio, cod_territorio, cod_indicador, grupo_edad, valor
    FROM silver.fact_proyeccion WHERE sexo = 'T' AND escenario = 'medio'
), ancho AS (
    SELECT nivel, anio, cod_territorio,
           max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '15-19')        AS pob_15_19,
           max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '60-64')        AS pob_60_64,
           max(valor) FILTER (WHERE cod_indicador = 'POBLACION' AND grupo_edad = '15-64')        AS pob_15_64,
           max(valor) FILTER (WHERE cod_indicador = 'DEPENDENCIA_VEJEZ' AND grupo_edad = 'TOTAL') AS dependencia_vejez,
           max(valor) FILTER (WHERE cod_indicador = 'TASA_DESEMPLEO' AND grupo_edad = '15+')      AS tasa_desempleo
    FROM base GROUP BY nivel, anio, cod_territorio
)
SELECT a.nivel, a.anio, a.cod_territorio, t.nombre_es AS territorio, t.tipo AS tipo_territorio,
       a.pob_15_19 / a.pob_60_64 * 100                                                       AS relevo_generacional,
       a.pob_15_64,
       (a.pob_15_64 / lag(a.pob_15_64) OVER (PARTITION BY a.cod_territorio ORDER BY a.anio) - 1) * 100 AS var_pob_15_64_pct,
       a.dependencia_vejez, a.tasa_desempleo
FROM ancho a JOIN silver.dim_territorio t USING (cod_territorio)
WHERE t.tipo IN ('nacional', 'sido', 'agregado') AND a.pob_15_64 IS NOT NULL;
