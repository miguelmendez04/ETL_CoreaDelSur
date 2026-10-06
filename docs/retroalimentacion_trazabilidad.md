# Retroalimentación del profesor: qué se cambió y dónde se ve

Cada comentario de la retroalimentación del Avance 1, el cambio que se hizo y dónde se puede verificar en el
repositorio o en la base de datos.

| # | Comentario | Cambio | Evidencia |
|---|---|---|---|
| R1 | Definir con más precisión el **grano** del dataset | Grano explícito por tabla: año × territorio × sexo × grupo de edad × indicador (+ edición y escenario en proyección), con clave primaria en PostgreSQL | [02_diseno.md §3](02_diseno.md#3-grano-y-claves); `sql/00_schemas.sql`; [diccionario_datos.md](diccionario_datos.md) |
| R2 | Diferenciar **análisis histórico, proyecciones oficiales e inferencias propias** | Tres tablas distintas (`fact_historico`, `fact_proyeccion`, `escenario_fuerza_laboral`) y columna `tipo_dato` en las vistas gold; en Power BI, línea continua para lo observado y punteada para proyección y escenarios | [02_diseno.md §2](02_diseno.md#2-tres-niveles-de-evidencia-siempre-separados); `gold.v_panel_indicadores.tipo_dato` |
| R3 | Fuentes solapadas: definir una **fuente maestra por indicador** | Catálogo maestra/contraste en `dim_indicador`; el contraste va a `silver.conciliacion` y nunca reemplaza el valor maestro; KPI de contrastes documentados | [fuentes_datos.md](fuentes_datos.md); `silver.conciliacion`; KPI `contrastes_documentados_pct` |
| R4 | La disponibilidad futura exige distinguir **proyección oficial vs modelo propio**; el ETL no produce proyecciones | La proyección es la de KOSTAT sin modificar; la fuerza laboral futura es un escenario contable con supuestos explícitos (A/B/C/D), versionados en `gold.supuestos` y con su sensibilidad | `gold.supuestos`; `gold.escenarios_sensibilidad`; README, "Supuestos del modelo" |
| R5 | El KPI **"0 % de inconsistencias"** está mal formulado | Tasa de registros válidos (≥ 98 %) y de rechazo (≤ 2 %) por carga, con el 100 % de rechazos trazados con regla y motivo | [03_validacion.md](03_validacion.md); `ctl.rechazos`; `ctl.kpis` |
| R6 | Confirmar que la **granularidad subnacional** es comparable | Completitud regional medida (99,5 %); coherencia de la suma de los 17 si-do con el total nacional (100 % de los años); agregado Chungnam + Sejong; homologación de Gangwon y Jeonbuk; la EAPS regional se interpreta como tendencia | KPIs `completitud_regional_pct` y `coherencia_territorial_pct`; `dim_territorio` |
| R7 | Definir **periodo, frecuencia, unidad y claves** antes de consolidar | `dim_indicador` con unidad, frecuencia original, fuente maestra, contraste y rango; frecuencia común anual (EAPS en promedio anual, población a mitad de año) | `config/mappings/indicadores.csv`; [diccionario_datos.md](diccionario_datos.md) |
| P1 | Prioridad: separar la serie histórica de las proyecciones en tablas distintas | = R2 | `silver.fact_historico` y `silver.fact_proyeccion` |
| P2 | Prioridad: KPIs de calidad con umbrales realistas | = R5; los 13 KPIs se calculan en cada ejecución | `gold.v_kpis_calidad` |
| H | Herramientas recomendadas: APIs, Python/Pandas, PostgreSQL, Power BI | OCDE, World Bank y UN WPP por API; KOSIS por descarga manual (su API exige residencia en Corea); PostgreSQL en Docker; Power BI sobre las vistas gold; orquestación con Airflow | `src/extract/`; `docker-compose.yml`; `powerbi/`; `airflow/` |

## Ajustes posteriores (revisión del equipo)

| Ajuste | Motivo | Evidencia |
|---|---|---|
| Población 2023–2025 marcada `preliminar` | KOSIS la publica desde su tabla de proyección | `silver.fact_historico.estado`; `tipo_dato = preliminar` |
| Escenarios de migración de KOSTAT | La migración es una palanca de política pública que el árbol de problemas menciona | `gold.v_proyeccion_escenarios`; hitos `cambio_pob_15_64_2025_2050_pct` |
| Defunciones, crecimiento natural y esperanza de vida | Completan la dinámica demográfica (el árbol cita la mayor longevidad como causa) | `v_panel_indicadores` |
| Supuesto D: cierre de la brecha de género | Es la palanca de participación con más margen en Corea | `gold.supuestos` (D) y su sensibilidad |
| Reemplazo laboral (15-24 / 55-64) y variante z-score del índice de riesgo | Indicadores del trabajo paralelo de una integrante del equipo, para contrastar resultados | `v_senales_escasez.reemplazo_laboral`; `riesgo_sensibilidad` (`seis_componentes_z`) |
| Diccionario de datos generado desde la base | Que la documentación no se desactualice respecto al esquema | `python -m src.quality.diccionario` |
| Tablero del equipo (diseño de Angie) sobre los datos del repo combinado | Un solo tablero, en Power BI y en versión web, alimentado por una capa de servicio en Python | `powerbi/`, `dashboard/`, `src/transform/gold/servicio_bi.py` |
| Escenarios de envejecimiento rápido y lento de KOSTAT | Completan los 8 escenarios oficiales del tablero | `silver.fact_proyeccion` |
| Calidad por dataset | La página de calidad muestra válidos y rechazos de cada dataset de bronze | `ctl.calidad_dataset` |
