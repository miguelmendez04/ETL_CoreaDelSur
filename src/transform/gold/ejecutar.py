"""Capa gold: desde silver calcula escenarios de fuerza laboral (6b), riesgo por si-do (5), asociaciones (7),
señales de escasez (8), sensibilidades y KPIs de calidad. Escribe en gold.* / ctl.kpis y exporta data/gold/.

Las vistas para Power BI (gold.v_*) están en sql/00_schemas.sql y leen silver y gold, así que se actualizan solas.
"""
import logging
import time

import pandas as pd

from src.load import archivos, ctl
from src.load import gold as carga
from src.quality import kpis
from src.transform.gold import analisis, escenarios, riesgo
from src.utils.config import cargar_config
from src.utils.db import conectar

log = logging.getLogger("gold")


def calcular(hist: pd.DataFrame, proy: pd.DataFrame, dims: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    """Todo el cálculo de gold, sin tocar la base."""
    esc, sup = escenarios.calcular(hist, proy, cfg)
    rie = riesgo.calcular(hist, proy, dims, cfg)
    return {
        "gold.supuestos": sup,
        "gold.escenario_fuerza_laboral": esc[["anio", "escenario_kostat", "id_supuesto", "version_modelo", "sexo",
                                              "grupo_edad", "poblacion", "factor_cobertura", "tasa_participacion",
                                              "fuerza_laboral"]],
        "gold.escenarios_sensibilidad": escenarios.sensibilidad(hist, proy, cfg),
        "gold.indicadores_riesgo": rie,
        "gold.riesgo_sensibilidad": riesgo.sensibilidad(rie, cfg),
        "gold.asociaciones": analisis.asociaciones(hist, cfg["gold"]["asociaciones"]),
        "gold.hitos_escasez": analisis.hitos(hist, proy, esc, cfg).fillna({"id_supuesto": "-"}),
    }


def _resumen(datos: dict, dims: pd.DataFrame, k: pd.DataFrame) -> None:
    esc, h = datos["gold.escenario_fuerza_laboral"], datos["gold.hitos_escasez"]
    fl = (esc.groupby(["anio", "escenario_kostat", "id_supuesto"])["fuerza_laboral"].sum() / 1e6).round(2)
    log.info("Fuerza laboral potencial (millones):\n%s", fl.unstack(["escenario_kostat", "id_supuesto"]).loc[[2026, 2035, 2050, 2072]].to_string())
    nombres = dims.set_index("cod_territorio")["nombre_es"]
    rie = datos["gold.indicadores_riesgo"].assign(si_do=lambda d: d["cod_territorio"].map(nombres))
    log.info("Riesgo demográfico por si-do (top 5):\n%s", rie[["ranking", "si_do", "indice_riesgo"]].head().round(1).to_string(index=False))
    senales = h[(h["escenario_kostat"] == "medio") & (h["id_supuesto"] == "-")]
    log.info("Señales de escasez (escenario medio):\n%s", senales[["hito", "anio", "valor"]].round(1).to_string(index=False))
    log.info("Asociaciones (Corea 2000-2025):\n%s", datos["gold.asociaciones"].round(2).to_string(index=False))
    sens = datos["gold.riesgo_sensibilidad"].pivot(index="cod_territorio", columns="esquema", values="ranking")
    sens = sens[sens.min(axis=1) <= 5].rename(index=nombres).sort_values("base")
    log.info("Sensibilidad del ranking de riesgo (si-do que entran al top 5 en algún esquema):\n%s", sens.to_string())
    log.info("KPIs de calidad:\n%s", k[["kpi", "valor", "meta", "cumple"]].to_string(index=False))


def ejecutar_gold() -> pd.DataFrame:
    cfg = cargar_config()
    inicio = time.perf_counter()
    conn = conectar()
    ids = {}
    try:
        log.info("Capa gold: desde silver")
        hist, proy = ctl.leer_tabla(conn, "silver.fact_historico"), ctl.leer_tabla(conn, "silver.fact_proyeccion")
        if hist.empty:
            raise LookupError("silver está vacío. Correr antes: python main.py --capa silver")
        dims = ctl.leer_tabla(conn, "silver.dim_territorio")
        ids = {t: ctl.abrir_carga(conn, "gold", t) for t in carga.TABLAS if t != "gold.supuestos"}
        ids["ctl.kpis"] = ctl.abrir_carga(conn, "gold", "ctl.kpis")

        datos = calcular(hist, proy, dims, cfg)
        carga.escribir(conn, datos, ids)
        for tabla, df in datos.items():
            if tabla in ids:
                ctl.cerrar_carga(conn, ids[tabla], "exito", len(df), len(df), 0)

        k = kpis.calcular(conn, cfg)
        carga.escribir_kpis(conn, k, ids["ctl.kpis"])
        ctl.cerrar_carga(conn, ids["ctl.kpis"], "exito", len(k), len(k), 0)

        m = archivos.exportar(conn, "gold", carga.TABLAS + carga.VISTAS, ids, csv=True)   # v_kpis_calidad = KPIs de esta corrida
        _resumen(datos, dims, k)
        log.info("Gold listo (%.1fs). Archivos: %s (%d archivos)", time.perf_counter() - inicio,
                 m["archivos"][0]["archivo"].rsplit("/", 1)[0], len(m["archivos"]))
        return k
    except Exception as e:
        ctl.marcar_fallo(conn, ids, e)
        raise
    finally:
        conn.close()
