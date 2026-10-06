"""
# ETL Corea del Sur: natalidad, envejecimiento y fuerza laboral

Orquesta el pipeline medallón con las mismas funciones que `python main.py`; este DAG no tiene lógica de datos:

```
bronze_worldbank ┐
bronze_oecd      ├─> silver ─> gold ─> verificar_kpis
bronze_unwpp     │
bronze_kosis     ┘
```

- **bronze_<fuente>**: extrae una fuente (las cuatro en paralelo). Si el crudo no cambió, la carga queda `omitido`
  y no se duplica, así que repetir una tarea es seguro.
- **silver**: reconstruye silver completo desde bronze, en una transacción. Solo corre si todas las fuentes
  terminaron bien.
- **gold**: escenarios, riesgo por si-do, señales, KPIs y exportación a `data/gold/`.
- **verificar_kpis**: falla (rojo) si algún KPI de calidad no cumple su meta.

Cada ejecución queda también en `ctl.log_cargas` de PostgreSQL, igual que al correr `main.py`.
"""
from datetime import datetime, timedelta

from airflow.sdk import dag, task

FUENTES = {"worldbank": "World Bank WDI (API v2): comparación internacional y contraste",
           "oecd": "OECD (API SDMX): productividad, fuerza laboral, fecundidad y participación por edad y sexo",
           "unwpp": "UN WPP 2024 (Data Portal API): contraste de proyecciones de población",
           "kosis": "KOSIS (descarga manual en data/bronze/kosis/): fuente maestra de Corea"}


@dag(
    dag_id="etl_corea",
    description="Pipeline medallón bronze -> silver -> gold (KOSIS, OECD, World Bank, UN WPP)",
    schedule="@weekly",                 # las fuentes son anuales o mensuales: una vez por semana basta
    start_date=datetime(2026, 10, 1),
    catchup=False,                      # no recupera semanas pasadas al activarlo
    max_active_runs=1,                  # nunca dos ejecuciones a la vez sobre la misma base
    default_args={"owner": "grupo_6", "retries": 2, "retry_delay": timedelta(minutes=5),   # p. ej. una API caída un momento
                  "execution_timeout": timedelta(minutes=30)},
    tags=["etl", "medallon", "corea"],
    doc_md=__doc__,
)
def etl_corea():
    # Los imports del proyecto van dentro de cada tarea: Airflow lee este archivo cada pocos segundos para
    # detectar cambios, y cargar pandas aquí lo haría lento.

    def bronze(fuente: str):
        @task(task_id=f"bronze_{fuente}",
              doc_md=f"**Capa bronze** · {FUENTES[fuente]}. Guarda el crudo en `data/bronze/` y en `bronze.*`; "
                     "si no cambió desde la última carga, queda `omitido` (no se duplica).")
        def extraer() -> dict:
            from src.extract.ejecutar import ejecutar_bronze
            resumen = ejecutar_bronze(fuentes=[fuente])
            fallos = resumen[resumen["estado"] == "fallo"]
            if not fallos.empty:
                raise RuntimeError(f"Fallaron {len(fallos)} datasets de {fuente}: "
                                   + "; ".join(f"{r.dataset}: {r.detalle}" for r in fallos.itertuples()))
            return {estado: int(n) for estado, n in resumen["estado"].value_counts().items()}
        return extraer()

    @task(doc_md="**Capa silver** · Normaliza, homologa y valida todo bronze; rechazos con motivo en "
                 "`ctl.rechazos`; derivados y conciliación. Reconstrucción completa en una transacción.")
    def silver() -> dict:
        from src.transform.silver.ejecutar import ejecutar_silver
        resumen = ejecutar_silver()
        return {r.tabla: {"filas": int(r.filas), "rechazadas": int(r.rechazadas)} for r in resumen.itertuples()}

    @task(doc_md="**Capa gold** · Escenarios A/B/C de fuerza laboral, riesgo por si-do, asociaciones, "
                 "señales de escasez, KPIs y exportación a `data/gold/` (Parquet y CSV).")
    def gold() -> int:
        from src.transform.gold.ejecutar import ejecutar_gold
        return len(ejecutar_gold())

    @task(doc_md="**Control de calidad** · Falla si algún KPI de `gold.v_kpis_calidad` no cumple su meta.")
    def verificar_kpis() -> dict:
        from src.load.ctl import leer_tabla
        from src.utils.db import conectar
        conn = conectar()
        try:
            k = leer_tabla(conn, "gold.v_kpis_calidad")
        finally:
            conn.close()
        no_cumplen = k[~k["cumple"]]
        if not no_cumplen.empty:
            raise ValueError("KPIs que no cumplen su meta: " + "; ".join(
                f"{r.kpi} = {r.valor} (meta {r.meta})" for r in no_cumplen.itertuples()))
        return {"kpis_cumplidos": f"{len(k)} de {len(k)}"}

    [bronze(f) for f in FUENTES] >> silver() >> gold() >> verificar_kpis()


etl_corea()
