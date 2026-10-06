"""Escritura de la capa gold en PostgreSQL (una transacción: se reemplaza completa o no se toca)."""
import json

import pandas as pd
import psycopg

from src.load.ctl import copiar

# Orden de inserción (supuestos antes que escenarios por la llave foránea).
TABLAS = ["gold.supuestos", "gold.escenario_fuerza_laboral", "gold.escenarios_sensibilidad", "gold.indicadores_riesgo",
          "gold.riesgo_sensibilidad", "gold.asociaciones", "gold.hitos_escasez"]
VISTAS = ["gold.v_panel_indicadores", "gold.v_escenarios_resumen", "gold.v_natalidad_vs_15_64",
          "gold.v_senales_escasez", "gold.v_conciliacion", "gold.v_kpis_calidad"]


def escribir(conn: psycopg.Connection, datos: dict[str, pd.DataFrame], ids: dict[str, int]) -> None:
    """datos: {tabla gold: DataFrame}. Cada fila lleva el id_carga de su tabla (supuestos usa el de escenarios)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(TABLAS))
        for tabla in TABLAS:
            df = datos[tabla].copy()
            if "parametros" in df:
                df["parametros"] = df["parametros"].map(lambda p: json.dumps(p, ensure_ascii=False))
            df["id_carga"] = ids["gold.escenario_fuerza_laboral" if tabla == "gold.supuestos" else tabla]
            copiar(cur, tabla, df, list(df.columns))


def escribir_kpis(conn: psycopg.Connection, kpis: pd.DataFrame, id_carga: int) -> None:
    with conn.transaction(), conn.cursor() as cur:
        copiar(cur, "ctl.kpis", kpis.assign(id_carga=id_carga), ["id_carga", "kpi", "valor", "meta", "cumple", "detalle"])
