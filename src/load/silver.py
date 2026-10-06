"""Escritura de la capa silver y de sus rechazos en PostgreSQL.

Silver es una función determinista de la última versión de bronze, así que se reconstruye completa en una sola
transacción: si algo falla, queda la versión anterior intacta. Gold depende de silver (llaves foráneas a las
dimensiones), así que también se vacía y queda pendiente de la capa gold.
"""
import json

import pandas as pd
import psycopg

from src.load.ctl import copiar

COLS_HIST = ["anio", "cod_territorio", "sexo", "grupo_edad", "cod_indicador", "valor", "fuente", "fecha_extraccion",
             "version_publicacion", "estado", "id_carga", "id_carga_origen"]
COLS_PROY = COLS_HIST[:5] + ["edicion_proyeccion", "escenario"] + COLS_HIST[5:]
COLS_CONC = ["nivel", "anio", "cod_territorio", "sexo", "grupo_edad", "cod_indicador", "escenario", "fuente_maestra",
             "fuente_contraste", "valor_maestra", "valor_contraste", "id_carga"]
DIMENSIONES = {
    "silver.dim_territorio": ("territorio", ["cod_territorio", "nombre_es", "nombre_en", "nombre_ko", "tipo", "cod_kosis",
                                             "cod_kosis_alt", "iso3", "vigente_desde", "vigente_hasta", "observacion"]),
    "silver.dim_edad": ("edad", ["cod_grupo_edad", "edad_min", "edad_max", "tipo", "orden"]),
    "silver.dim_sexo": ("sexo", ["cod_sexo", "nombre", "cod_kosis", "cod_worldbank", "cod_oecd"]),
    "silver.dim_indicador": ("indicador", ["cod_indicador", "nombre", "definicion", "unidad", "frecuencia_original",
                                           "fuente_maestra", "fuente_contraste", "es_derivado", "rango_min", "rango_max"]),
}


def escribir(conn: psycopg.Connection, dims: dict, hist: pd.DataFrame, proy: pd.DataFrame, conc: pd.DataFrame,
             rechazos: pd.DataFrame, pasos: pd.DataFrame, calidad: pd.DataFrame | None = None) -> None:
    """Reemplaza el contenido de silver (dimensiones, hechos y conciliación) y agrega a ctl los rechazos y el
    embudo de pasos de esta ejecución."""
    with conn.transaction(), conn.cursor() as cur:
        # Gold depende de silver (llaves foráneas a las dimensiones): queda vacío hasta correr la capa gold.
        cur.execute("TRUNCATE gold.escenario_fuerza_laboral, gold.supuestos, gold.indicadores_riesgo, "
                    "gold.asociaciones, gold.hitos_escasez, gold.riesgo_sensibilidad, gold.escenarios_sensibilidad, "
                    "silver.conciliacion, silver.fact_historico, silver.fact_proyeccion, "
                    "silver.dim_territorio, silver.dim_edad, silver.dim_sexo, silver.dim_indicador")
        for tabla, (clave, columnas) in DIMENSIONES.items():
            d = dims[clave].replace("", None)
            copiar(cur, tabla, d, columnas)
        copiar(cur, "silver.fact_historico", hist, COLS_HIST)
        copiar(cur, "silver.fact_proyeccion", proy, COLS_PROY)
        copiar(cur, "silver.conciliacion", conc, COLS_CONC)
        if not rechazos.empty:
            r = rechazos.assign(registro=rechazos["registro"].map(lambda x: json.dumps(x, ensure_ascii=False, default=str)))
            copiar(cur, "ctl.rechazos", r, ["id_carga", "tabla_origen", "id_registro_origen", "regla", "motivo", "registro"])
        copiar(cur, "ctl.pasos_silver", pasos, ["id_carga", "orden", "paso", "tipo", "filas", "variacion", "en_embudo",
                                                "descripcion"])
        if calidad is not None and not calidad.empty:
            copiar(cur, "ctl.calidad_dataset", calidad, ["id_carga", "fuente", "dataset", "registros_evaluados",
                                                         "registros_validos", "registros_rechazados"])


TABLAS = ["silver.fact_historico", "silver.fact_proyeccion", "silver.conciliacion",
          "silver.dim_territorio", "silver.dim_edad", "silver.dim_sexo", "silver.dim_indicador"]
