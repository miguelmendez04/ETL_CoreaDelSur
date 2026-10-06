"""KPIs de calidad (CLAUDE.md, sección 7), calculados desde ctl y silver. Se guardan en ctl.kpis por ejecución."""
import pandas as pd
import psycopg


def _uno(conn: psycopg.Connection, consulta: str):
    with conn.cursor() as cur:
        cur.execute(consulta)
        return cur.fetchone()


def _completitud(conn: psycopg.Connection, tipo: str, indicadores: list[str], ini: int, fin: int) -> float:
    """% de celdas año × territorio × indicador con dato (sexo total, edad total). Los años anteriores a la
    creación de un territorio (Sejong antes de 2012) no se esperan."""
    lista = ", ".join(f"'{i}'" for i in indicadores)
    esperado, presente = _uno(conn, f"""
        WITH esperadas AS (
            SELECT t.cod_territorio, i.cod_indicador, a.anio
            FROM silver.dim_territorio t
            CROSS JOIN (SELECT unnest(ARRAY[{lista}]) AS cod_indicador) i
            CROSS JOIN generate_series({ini}, {fin}) AS a(anio)
            WHERE t.tipo = '{tipo}' AND a.anio >= coalesce(t.vigente_desde, 0))
        SELECT count(*), count(f.valor) FROM esperadas e
        LEFT JOIN silver.fact_historico f ON f.cod_territorio = e.cod_territorio AND f.cod_indicador = e.cod_indicador
             AND f.anio = e.anio AND f.sexo = 'T' AND f.grupo_edad IN ('TOTAL', '15+')""")
    return presente / esperado * 100


def calcular(conn: psycopg.Connection, cfg: dict) -> pd.DataFrame:
    ini, fin = cfg["periodo_historico"]["inicio"], cfg["periodo_historico"]["fin"]
    tol = cfg["calidad"]["tolerancia_conciliacion_pct"]
    nacionales = ["NACIMIENTOS", "TFR", "POBLACION", "POB_ACTIVA", "OCUPADOS", "TASA_PARTICIPACION",
                  "TASA_DESEMPLEO", "PROP_65MAS", "INDICE_ENVEJECIMIENTO", "DEPENDENCIA_VEJEZ", "PIB_HORA"]
    regionales = [i for i in nacionales if i != "PIB_HORA"]

    fuentes = _uno(conn, "SELECT count(DISTINCT fuente) FROM ctl.log_cargas WHERE capa = 'bronze' AND estado = 'exito'")[0]
    usados, documentados = _uno(conn, """SELECT count(DISTINCT u.cod_indicador), count(DISTINCT i.cod_indicador)
        FROM (SELECT cod_indicador FROM silver.fact_historico UNION SELECT cod_indicador FROM silver.fact_proyeccion) u
        LEFT JOIN silver.dim_indicador i ON i.cod_indicador = u.cod_indicador AND i.definicion <> ''""")
    total_ej, sin_fallo = _uno(conn, "SELECT count(*), count(*) FILTER (WHERE estado <> 'fallo') FROM ctl.log_cargas WHERE estado <> 'en_curso'")
    extraidas, validas, rechazadas = _uno(conn, """SELECT sum(filas_extraidas), sum(filas_validas), sum(filas_rechazadas)
        FROM ctl.log_cargas WHERE capa = 'silver' AND estado = 'exito'
          AND id_carga IN (SELECT max(id_carga) FROM ctl.log_cargas WHERE capa = 'silver' AND estado = 'exito' GROUP BY dataset)""")
    rech_total, rech_con_motivo = _uno(conn, """SELECT count(*), count(*) FILTER (WHERE coalesce(motivo, '') <> '')
        FROM ctl.rechazos WHERE id_carga IN (SELECT max(id_carga) FROM ctl.log_cargas WHERE capa = 'silver' AND estado = 'exito' GROUP BY dataset)""")
    dup_bronze = _uno(conn, """SELECT coalesce(sum(n - 1), 0) FROM (
        SELECT id_carga, hash_registro, count(*) n FROM (
            SELECT id_carga, hash_registro FROM bronze.kosis UNION ALL SELECT id_carga, hash_registro FROM bronze.worldbank_wdi
            UNION ALL SELECT id_carga, hash_registro FROM bronze.oecd_sdmx UNION ALL SELECT id_carga, hash_registro FROM bronze.unwpp_wpp2024) b
        GROUP BY 1, 2 HAVING count(*) > 1) d""")[0]
    proy_total, proy_ok = _uno(conn, """SELECT count(*), count(*) FILTER (WHERE edicion_proyeccion IS NOT NULL AND escenario IS NOT NULL)
        FROM silver.fact_proyeccion""")
    pares, dentro = _uno(conn, f"""SELECT count(*), count(*) FILTER (WHERE abs(dif_pct) <= {tol})
        FROM silver.conciliacion WHERE nivel = 'historico'""")

    pct = lambda a, b: round(a / b * 100, 2) if b else None
    filas = [
        ("fuentes_institucionales", fuentes, ">= 3", fuentes >= 3, "fuentes con carga bronze exitosa"),
        ("indicadores_documentados_pct", pct(documentados, usados), "100 %", documentados == usados,
         f"{documentados} de {usados} indicadores en silver con definición en dim_indicador"),
        ("ejecuciones_sin_fallo_pct", pct(sin_fallo, total_ej), ">= 95 %", pct(sin_fallo, total_ej) >= 95,
         f"{sin_fallo} de {total_ej} cargas registradas en ctl.log_cargas"),
        ("registros_validos_pct", pct(validas, extraidas), ">= 98 %", pct(validas, extraidas) >= 98,
         f"última carga silver: {validas} válidos de {extraidas}"),
        ("tasa_rechazo_pct", pct(rechazadas, extraidas), "<= 2 %", pct(rechazadas, extraidas) <= 2,
         f"{rechazadas} rechazados; {pct(rech_con_motivo, rech_total) if rech_total else 100} % con motivo"),
        ("rechazos_con_motivo_pct", pct(rech_con_motivo, rech_total) if rech_total else 100.0, "100 %",
         rech_con_motivo == rech_total, "rechazos de la última carga silver trazados con regla y motivo"),
        ("completitud_nacional_pct", round(_completitud(conn, "nacional", nacionales, ini, fin), 2), ">= 95 %", None,
         f"{len(nacionales)} indicadores × {fin - ini + 1} años, Corea"),
        ("completitud_regional_pct", round(_completitud(conn, "sido", regionales, ini, fin), 2), ">= 90 %", None,
         f"{len(regionales)} indicadores × años × 17 si-do (desde que cada uno existe)"),
        ("duplicados_bronze", dup_bronze, "se monitorean", True, "registros con hash repetido dentro de una misma carga"),
        ("proyeccion_con_edicion_escenario_pct", pct(proy_ok, proy_total), "100 %", proy_ok == proy_total,
         f"{proy_total} registros en silver.fact_proyeccion"),
        ("conciliacion_dentro_tolerancia_pct", pct(dentro, pares), ">= 90 %", pct(dentro, pares) >= 90,
         f"{dentro} de {pares} pares históricos con |dif| <= {tol} %"),
    ]
    df = pd.DataFrame(filas, columns=["kpi", "valor", "meta", "cumple", "detalle"])
    umbral = {"completitud_nacional_pct": 95, "completitud_regional_pct": 90}
    for k, u in umbral.items():
        df.loc[df["kpi"] == k, "cumple"] = df.loc[df["kpi"] == k, "valor"] >= u
    df["cumple"] = df["cumple"].astype(bool)
    return df
