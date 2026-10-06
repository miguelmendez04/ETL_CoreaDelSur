# Fuentes de datos

Regla general: **una fuente maestra por indicador**. Las demás fuentes solo sirven de contraste: se cargan en
`silver.conciliacion` y nunca reemplazan un valor maestro. Todo el catálogo está en `config/config.yaml`; agregar un
indicador o una tabla es una entrada nueva en el catálogo, no código nuevo.

## Fuentes y rol

| Fuente | Organismo | Rol | Acceso | Tabla bronze |
|---|---|---|---|---|
| KOSIS | KOSTAT (Statistics Korea) | Maestra: histórico nacional y por si-do, y proyecciones oficiales | Descarga manual de CSV desde [kosis.kr/eng](https://kosis.kr/eng/) (la OpenAPI está restringida a residentes de Corea) | `bronze.kosis` |
| OECD | OCDE | Maestra de productividad (PIB por hora); contraste de nacimientos, fecundidad y EAPS; promedio OCDE para el supuesto C | API SDMX pública, sin clave ([sdmx.oecd.org](https://sdmx.oecd.org/public/rest/)) | `bronze.oecd_sdmx` |
| World Bank WDI | Banco Mundial | Contraste y comparación internacional (Corea, Japón, EE. UU., Alemania, Italia, España, Francia, China y OCDE) | API v2 sin clave ([api.worldbank.org/v2](https://api.worldbank.org/v2/)) | `bronze.worldbank_wdi` |
| UN WPP 2024 | Naciones Unidas | Solo contraste de población histórica y proyectada | Data Portal API con token gratuito (`UNWPP_API_TOKEN` en `.env`) | `bronze.unwpp_wpp2024` |

El Ministerio de Empleo y Trabajo de Corea quedó fuera del alcance: sus series de empleo administrativo no agregan
nada a la EAPS para la pregunta del proyecto.

## Tablas de KOSIS

| Dataset (`config.yaml`) | tblId | Tabla en KOSIS | Periodo | Indicadores que aporta |
|---|---|---|---|---|
| `vitales_nacional` | DT_1B8000F | Vital Statistics of Korea | 2000–2025 | Esperanza de vida al nacer por sexo |
| `vitales_sido` | DT_1B8000G | Vital statistics by Month for Provinces | 2000–2025 | Nacimientos, defunciones, crecimiento natural (nacional y 17 si-do) |
| `tfr_sido` | DT_1B81A17 | Total Fertility Rates for city, county and district | 2000–2025 | TFR nacional y por si-do |
| `eaps_sido` | DT_1DA7004S | Summary of economically active population by city/province | 2000–2025 | Población 15+, activa, ocupados, participación y desempleo por si-do |
| `eaps_sexo_edad` | DT_1DA7012S | Summary of economically active pop. by gender/age group | 2000–2025 | Los mismos indicadores por sexo y grupo de edad (nacional) |
| `poblacion_nacional` | DT_1BPA001 | Projected Population by Age (Korea) | 2000–2072 | Población por sexo y edad quinquenal (2000–2025 histórico; 2026+ proyección media) |
| `poblacion_sido` | DT_1BPB001 | Projected Population by Age (Province) | 2000–2052 | Población por si-do, sexo y edad (2026+ proyección media) |
| `proyeccion_escenarios` | sin tblId publicado | Projected population by scenario, sex and age (Korea) | 2022–2072 | Población proyectada en los escenarios de fecundidad (alto/bajo), de migración (alta, baja, sin migración) y de envejecimiento (rápido, lento) |
| `proyeccion_resumen` | DT_1BPA002 | Population Projections and Summary Indicators (Korea) | 2022–2072 | Indicadores resumen de la proyección; queda en bronze como referencia (los derivados se calculan en el pipeline) |

La tabla de proyección por escenario se descargó desde la publicación de KOSTAT en KOSIS, pero el portal no muestra
su `tblId`. El extractor no lo necesita: identifica el archivo por su patrón de nombre, verifica el encoding (cp949),
las columnas de dimensión y los años, y guarda la URL y el sha256 en el metadata. El `tblId` queda vacío y
documentado en `config.yaml`.

## Indicadores del World Bank

| Código | Indicador interno | Nota |
|---|---|---|
| `SP.DYN.TFRT.IN` | TFR | |
| `SP.POP.TOTL`, `SP.POP.0014.TO`, `SP.POP.1564.TO`, `SP.POP.65UP.TO` | POBLACION | total y grupos 0-14, 15-64, 65+ |
| `SP.POP.65UP.TO.ZS` | PROP_65MAS | |
| `SP.POP.DPND.OL` | DEPENDENCIA_VEJEZ | 65+ / 15-64, comparable con la nuestra |
| `SL.TLF.CACT.ZS` | TASA_PARTICIPACION | estimación modelada de la OIT |
| `SP.DYN.CBRT.IN` | NACIMIENTOS | tasa bruta × población / 1000 |
| `SL.GDP.PCAP.EM.KD` | PIB_OCUPADO | comparación internacional de productividad |

## Datasets de la OCDE

| Dataset (`config.yaml`) | Dataflow | Uso |
|---|---|---|
| `productividad` | `OECD.SDD.TPS,DSD_PDB@DF_PDB` | PIB por hora trabajada (maestra) |
| `fuerza_laboral` | `OECD.SDD.TPS,DSD_ALFS@DF_SUMTAB` | Población activa, ocupados y desempleo (contraste) |
| `fecundidad_nacimientos` | `OECD.CFE.EDS,DSD_REG_DEMO@DF_FERTILITY` | Nacimientos y TFR (contraste) |
| `participacion_edad_sexo` | `OECD.SDD.TPS,DSD_LFS@DF_IALFS_LF_WAP_Q` | Participación por sexo y edad de Corea y del promedio OCDE (supuesto C) |
| `dependencia_vejez` | `OECD.ELS.SAE,DSD_POPULATION@DF_POP_HIST` | Solo bronze: la OCDE la mide como 65+ / 20-64 |

## Fuente maestra por indicador

| Indicador | Maestra | Contraste | Periodo | Frecuencia | Unidad | Territorio |
|---|---|---|---|---|---|---|
| Nacimientos | KOSIS – Estadísticas vitales | OECD, WB | 2000–2025 | Anual | personas | Nacional + 17 si-do |
| Defunciones y crecimiento natural | KOSIS – Estadísticas vitales | — | 2000–2025 | Anual | personas | Nacional + 17 si-do |
| Esperanza de vida al nacer | KOSIS – Estadísticas vitales | — | 2000–2024 | Anual | años | Nacional |
| Tasa global de fecundidad | KOSIS – Estadísticas vitales | OECD, WB | 2000–2025 | Anual | hijos por mujer | Nacional + si-do |
| Población por sexo y edad | KOSIS – Población estimada | UN WPP, WB | 2000–2025 | Anual (mitad de año) | personas | Nacional + si-do |
| Población activa, ocupados, participación, desempleo | KOSIS – EAPS | OECD, WB | 2000–2025 | Mensual → promedio anual publicado | personas; % | Nacional + si-do |
| Proporción 65+, índice de envejecimiento, dependencia de vejez | Calculados en el pipeline | WB | 2000–2025 | Anual | %; ratio × 100 | Nacional + si-do |
| PIB por hora trabajada | OECD Productivity | — | 2000–último | Anual | USD PPA constantes | Nacional |
| PIB por ocupado (comparación) | World Bank | — | 2000–2025 | Anual | USD PPA constantes | Países |
| Población proyectada por sexo y edad | KOSTAT Proyecciones | UN WPP 2024 | 2026–2072 (nacional); 2026–2052 (si-do) | Anual | personas | Nacional + si-do |

## Particularidades que condicionan el uso

- **Población 2023–2025:** las tablas DT_1BPA001/DT_1BPB001 son de proyección. KOSTAT publica la población estimada
  hasta el último año con registros; en los años más recientes el valor es el del escenario medio. Esos años quedan
  como `estado = preliminar` y en las vistas gold con `tipo_dato = preliminar`, nunca como proyección propia.
- **EAPS regional:** encuesta por muestreo; mayor error en si-do pequeños. Se interpreta como tendencia.
- **Sejong** existe desde 2012 (antes era parte de Chungcheongnam-do) y la EAPS lo publica desde 2017. Para las
  series 2000–2025 se usa el agregado Chungnam + Sejong; las tasas se recalculan desde los niveles.
- **Gangwon y Jeonbuk** cambiaron de nombre oficial (2023 y 2024); `dim_territorio` guarda ambos códigos.
- **Dependencia de vejez de la OCDE** = 65+ / 20-64: no es comparable 1 a 1 y no se concilia; la nuestra es
  65+ / 15-64, igual que la del World Bank.
- **Escenarios de KOSTAT:** en este proyecto `alto` y `bajo` son las variantes de *solo fecundidad* (mortalidad y
  migración medias), no los escenarios compuestos de KOSTAT; en los tableros se rotulan "fecundidad alta/baja".
  `migracion_alta`, `migracion_baja` y `sin_migracion` cambian solo la migración internacional;
  `envejecimiento_rapido` (fecundidad baja, esperanza de vida alta, migración baja) y `envejecimiento_lento` (lo
  contrario) combinan los tres componentes. Con el medio son 8 escenarios; los otros 21 del archivo quedan en bronze.
- **UN WPP** y KOSTAT usan supuestos distintos de fecundidad y migración: en proyección la diferencia se guarda
  como contraste, no como error.
