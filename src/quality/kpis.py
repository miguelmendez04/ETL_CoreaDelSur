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
    with conn.cursor() as cur:   # meta "por carga": cada tabla de la última ejecución de silver por separado
        cur.execute("""SELECT dataset, filas_extraidas, filas_validas, filas_rechazadas FROM ctl.log_cargas
            WHERE id_carga IN (SELECT max(id_carga) FROM ctl.log_cargas WHERE capa = 'silver' AND estado = 'exito' GROUP BY dataset)
            ORDER BY dataset""")
        por_carga = pd.DataFrame(cur.fetchall(), columns=["dataset", "extraidas", "validas", "rechazadas"])
    por_carga["validos_pct"] = (por_carga["validas"] / por_carga["extraidas"] * 100).round(2)
    por_carga["rechazo_pct"] = (por_carga["rechazadas"] / por_carga["extraidas"] * 100).round(2)
    peor = por_carga.loc[por_carga["rechazo_pct"].idxmax()]
    detalle = "; ".join(f"{r.dataset.split('.')[1]} {r.rechazadas} de {r.extraidas} ({r.rechazo_pct} %)"
                        for r in por_carga.itertuples())
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

    lista = ", ".join(f"'{i}'" for i in cfg["calidad"]["coherencia_territorial"])
    tol_suma = cfg["calidad"]["tolerancia_suma_edades_pct"]
    celdas, coherentes, dif_max = _uno(conn, f"""
        WITH sido AS (SELECT f.cod_indicador, f.anio, sum(f.valor) AS suma FROM silver.fact_historico f
                      JOIN silver.dim_territorio t ON t.cod_territorio = f.cod_territorio AND t.tipo = 'sido'
                      WHERE f.fuente = 'KOSIS' AND f.sexo = 'T' AND f.grupo_edad IN ('TOTAL', '15+')
                        AND f.cod_indicador IN ({lista}) GROUP BY 1, 2),
             d AS (SELECT abs(s.suma - n.valor) / n.valor * 100 AS dif FROM sido s
                   JOIN silver.fact_historico n ON n.cod_territorio = '00' AND n.fuente = 'KOSIS' AND n.sexo = 'T'
                    AND n.grupo_edad IN ('TOTAL', '15+') AND n.cod_indicador = s.cod_indicador AND n.anio = s.anio)
        SELECT count(*), count(*) FILTER (WHERE dif <= {tol_suma}), round(max(dif)::numeric, 3) FROM d""")

    with conn.cursor() as cur:   # el diccionario declara los mismos contrastes que se concilian de verdad
        cur.execute("""SELECT cod_indicador, trim(unnest(string_to_array(fuente_contraste, ';'))) FROM silver.dim_indicador
                       WHERE coalesce(fuente_contraste, '') <> ''""")
        declarados = set(cur.fetchall())
        cur.execute("SELECT DISTINCT cod_indicador, fuente_contraste FROM silver.conciliacion")
        conciliados = set(cur.fetchall())
    contraste_ok = declarados == conciliados
    contraste_det = ("los contrastes de dim_indicador coinciden con silver.conciliacion" if contraste_ok else
                     f"declarados sin conciliar: {sorted(declarados - conciliados)}; conciliados sin declarar: "
                     f"{sorted(conciliados - declarados)}")

    pct = lambda a, b: round(a / b * 100, 2) if b else None
    filas = [
        ("fuentes_institucionales", fuentes, ">= 3", fuentes >= 3, "fuentes con carga bronze exitosa"),
        ("indicadores_documentados_pct", pct(documentados, usados), "100 %", documentados == usados,
         f"{documentados} de {usados} indicadores en silver con definición en dim_indicador"),
        ("contrastes_documentados_pct", pct(len(declarados & conciliados), len(declarados | conciliados)), "100 %",
         contraste_ok, contraste_det),
        ("ejecuciones_sin_fallo_pct", pct(sin_fallo, total_ej), ">= 95 %", pct(sin_fallo, total_ej) >= 95,
         f"{sin_fallo} de {total_ej} cargas registradas en ctl.log_cargas"),
        ("registros_validos_pct", float(por_carga["validos_pct"].min()), ">= 98 % por carga",
         bool((por_carga["validos_pct"] >= 98).all()), f"peor carga: {peor['dataset']} ({peor['validos_pct']} % válidos)"),
        ("tasa_rechazo_pct", float(por_carga["rechazo_pct"].max()), "<= 2 % por carga",
         bool((por_carga["rechazo_pct"] <= 2).all()), f"rechazados por carga: {detalle}"),
        ("rechazos_con_motivo_pct", pct(rech_con_motivo, rech_total) if rech_total else 100.0, "100 %",
         rech_con_motivo == rech_total, "rechazos de la última carga silver trazados con regla y motivo"),
        ("completitud_nacional_pct", round(_completitud(conn, "nacional", nacionales, ini, fin), 2), ">= 95 %", None,
         f"{len(nacionales)} indicadores × {fin - ini + 1} años, Corea"),
        ("completitud_regional_pct", round(_completitud(conn, "sido", regionales, ini, fin), 2), ">= 90 %", None,
         f"{len(regionales)} indicadores × años × 17 si-do (desde que cada uno existe)"),
        ("coherencia_territorial_pct", pct(coherentes, celdas), "100 %", coherentes == celdas,
         f"{coherentes} de {celdas} año × indicador donde la suma de los 17 si-do difiere <= {tol_suma} % del nacional "
         f"(máx. {dif_max} %)"),
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
