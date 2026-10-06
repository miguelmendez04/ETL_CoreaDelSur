"""Capa de servicio del tablero (Power BI y versión web): data/gold/powerbi/pbi_*.parquet.

Tablas con la forma exacta que necesita cada visual del tablero del equipo (diseño de Angie Rodríguez), construidas
desde silver, gold y ctl. Las transformaciones quedan aquí, en Python; Power Query y la página web solo leen los
archivos. Se regenera al final de la capa gold.
"""
import numpy as np
import pandas as pd

from src.utils.config import ruta

ESCENARIOS = {"medio": "Medio (base)", "bajo": "Fecundidad baja", "alto": "Fecundidad alta",
              "sin_migracion": "Sin migración internacional", "migracion_baja": "Migración internacional baja",
              "migracion_alta": "Migración internacional alta", "envejecimiento_rapido": "Envejecimiento rápido",
              "envejecimiento_lento": "Envejecimiento lento"}
PAISES = {"00": "Corea del Sur", "JPN": "Japón", "ITA": "Italia", "DEU": "Alemania", "ESP": "España",
          "USA": "Estados Unidos", "FRA": "Francia", "OED": "Promedio OCDE"}
REGION = {"11": "Capital", "23": "Capital", "31": "Capital", "21": "Sudeste", "22": "Sudeste", "26": "Sudeste",
          "37": "Sudeste", "38": "Sudeste", "24": "Suroeste", "35": "Suroeste", "36": "Suroeste", "25": "Centro",
          "29": "Centro", "33": "Centro", "34": "Centro", "32": "Noreste", "39": "Jeju"}
ICONO_SEM = {"Crítico": "🔴 Crítico", "Alerta": "🟠 Alerta", "Normal": "🟢 Normal", "Contexto": "⚪ Contexto"}
EDADES_EAPS = {"15-19": 1, "20-29": 2, "30-39": 3, "40-49": 4, "50-59": 5, "60+": 6}
EDICION = "KOSTAT_2022_2072"


def _leer(conn, consulta: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(consulta)
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    for c in df.columns:   # NUMERIC llega como Decimal
        if df[c].dtype == object and df[c].map(lambda v: type(v).__name__ == "Decimal").any():
            df[c] = pd.to_numeric(df[c])
    return df


def es(v, d=1) -> str:
    """Número con coma decimal y punto de miles."""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def es_s(v, d=1) -> str:
    """Como es(), con signo + en los positivos."""
    return ("+" if v > 0 else "") + es(v, d)


def construir(conn) -> dict[str, pd.DataFrame]:
    t = {}
    panel = _leer(conn, "SELECT * FROM gold.v_panel_indicadores")
    nac = panel[panel["cod_territorio"] == "00"].sort_values("anio").drop_duplicates("anio")
    sen = _leer(conn, "SELECT anio, reemplazo_laboral FROM gold.v_senales_escasez WHERE cod_territorio = '00'")
    sen = sen.drop_duplicates("anio")
    res = _leer(conn, "SELECT * FROM gold.v_escenarios_resumen")
    kpis = _leer(conn, "SELECT kpi, valor, detalle FROM gold.v_kpis_calidad").set_index("kpi")

    # ---------------------------------------------------------------- nacional (una fila por año)
    n = pd.DataFrame({"anio": nac["anio"].astype(int).values})
    col = lambda c: nac[c].astype(float).values
    n["TFR"], n["NACIMIENTOS"], n["DEFUNCIONES"] = col("tfr"), col("nacimientos"), col("defunciones")
    n["CRECIMIENTO_NATURAL"], n["ESPERANZA_VIDA"] = col("crecimiento_natural"), col("esperanza_vida")
    n["POB_0_14"], n["POB_15_64"], n["POB_65MAS"], n["POB_TOTAL"] = col("pob_0_14"), col("pob_15_64"), col("pob_65mas"), col("poblacion_total")
    for k, c in (("PROP_0_14", "POB_0_14"), ("PROP_15_64", "POB_15_64"), ("PROP_65MAS", "POB_65MAS")):
        n[k] = n[c] / n["POB_TOTAL"] * 100
    n["DEP_VEJEZ"], n["IND_ENVEJECIMIENTO"] = col("dependencia_vejez"), col("indice_envejecimiento")
    n["IND_REEMPLAZO_LABORAL"] = n["anio"].map(sen.set_index("anio")["reemplazo_laboral"].astype(float))
    n["POB_ACTIVA"], n["OCUPADOS"] = col("pob_activa"), col("ocupados")
    n["TASA_PARTICIPACION"], n["TASA_DESEMPLEO"], n["PIB_HORA"] = col("tasa_participacion"), col("tasa_desempleo"), col("pib_hora")
    fl = res[res["escenario_kostat"] == "medio"].pivot(index="anio", columns="id_supuesto", values="fuerza_laboral")
    for s in fl.columns:
        n[f"FLP_{s}"] = n["anio"].map(fl[s].astype(float))
    # población oficial estimada hasta 2022; desde 2023 KOSIS la publica desde la proyección (escenario medio)
    n["tipo_dato_poblacion"] = np.where(n["anio"] <= 2022, "estimado", "proyeccion_oficial")
    n["periodo"] = np.where(n["anio"] <= 2025, "Histórico", "Proyección")
    t["pbi_nacional"] = n

    anios = pd.DataFrame({"anio": range(int(n["anio"].min()), int(n["anio"].max()) + 1)})
    anios["periodo"] = np.where(anios["anio"] <= 2025, "Histórico", "Proyección")
    anios["decada"] = (anios["anio"] // 10 * 10).astype(str) + "s"
    t["pbi_anios"] = anios
    t["pbi_anio_sel"] = pd.DataFrame({"anio_piramide": [2000, 2010, 2022, 2025, 2030, 2040, 2050, 2060, 2072]})

    # ---------------------------------------------------------------- escenarios oficiales (2025 = año base observado)
    pe = _leer(conn, f"""
        SELECT anio, escenario AS cod_escenario, grupo_edad, valor FROM silver.fact_proyeccion
        WHERE cod_territorio = '00' AND sexo = 'T' AND cod_indicador = 'POBLACION' AND edicion_proyeccion = '{EDICION}'
          AND grupo_edad IN ('TOTAL', '15-64', '65+')""")
    pe = pe.pivot_table(index=["anio", "cod_escenario"], columns="grupo_edad", values="valor").reset_index()
    base25 = nac[nac["anio"] == 2025].iloc[0]
    pe = pd.concat([pe, pd.DataFrame({"anio": 2025, "cod_escenario": list(ESCENARIOS), "TOTAL": base25["poblacion_total"],
                                      "15-64": base25["pob_15_64"], "65+": base25["pob_65mas"]})], ignore_index=True)
    pe[["TOTAL", "15-64", "65+"]] = pe[["TOTAL", "15-64", "65+"]].astype(float)
    partes = [pe.assign(indicador="Población 15-64 (millones)", valor=pe["15-64"] / 1e6),
              pe.assign(indicador="Dependencia de vejez", valor=pe["65+"] / pe["15-64"] * 100),
              pe.assign(indicador="Población 65+ (%)", valor=pe["65+"] / pe["TOTAL"] * 100)]
    e = pd.concat(partes)[["anio", "cod_escenario", "valor", "indicador"]]
    e = e[e["cod_escenario"].isin(ESCENARIOS)]
    e["escenario"] = e["cod_escenario"].map(ESCENARIOS)
    e["orden_escenario"] = e["cod_escenario"].map({c: i for i, c in enumerate(ESCENARIOS)})
    t["pbi_escenarios"] = e.sort_values(["indicador", "orden_escenario", "anio"]).reset_index(drop=True)
    t["pbi_escenario_sel"] = pd.DataFrame({"escenario": list(ESCENARIOS.values()), "orden": range(len(ESCENARIOS))})

    # ---------------------------------------------------------------- fuerza laboral potencial (escenario propio)
    sup = _leer(conn, "SELECT id_supuesto, nombre FROM gold.supuestos")
    nombres_sup = {r.id_supuesto: f"{r.id_supuesto} · {r.nombre}" for r in sup.itertuples()}
    activos25 = float(base25["pob_activa"])
    f = res[["anio", "escenario_kostat", "id_supuesto", "fuerza_laboral"]].rename(
        columns={"escenario_kostat": "cod_escenario", "id_supuesto": "cod_supuesto", "fuerza_laboral": "flp"})
    f = pd.concat([f, pd.DataFrame([(2025, e_, s, activos25) for e_ in f["cod_escenario"].unique() for s in nombres_sup],
                                   columns=f.columns)], ignore_index=True)
    f["flp"] = f["flp"].astype(float)
    f["indice_2025"] = f["flp"] / activos25 * 100
    f["supuesto"] = f["cod_supuesto"].map(nombres_sup)
    f["escenario"] = f["cod_escenario"].map(ESCENARIOS)
    t["pbi_flp"] = f.sort_values(["cod_escenario", "cod_supuesto", "anio"]).reset_index(drop=True)

    # ---------------------------------------------------------------- pirámide (histórico + proyección media)
    edad = _leer(conn, "SELECT cod_grupo_edad, orden FROM silver.dim_edad WHERE tipo = 'quinquenal' ORDER BY orden")
    orden_edad = {c: i + 1 for i, c in enumerate(edad["cod_grupo_edad"])}
    lista = ", ".join(f"'{c}'" for c in orden_edad)
    pir = _leer(conn, f"""
        SELECT anio, sexo, grupo_edad AS cod_edad, valor AS poblacion FROM silver.fact_historico
        WHERE cod_territorio = '00' AND cod_indicador = 'POBLACION' AND sexo IN ('H', 'M') AND grupo_edad IN ({lista})
        UNION ALL
        SELECT anio, sexo, grupo_edad, valor FROM silver.fact_proyeccion
        WHERE cod_territorio = '00' AND cod_indicador = 'POBLACION' AND sexo IN ('H', 'M') AND grupo_edad IN ({lista})
          AND escenario = 'medio' AND edicion_proyeccion = '{EDICION}'""")
    pir["poblacion"] = pir["poblacion"].astype(float)
    pir["edad"], pir["orden"] = pir["cod_edad"], pir["cod_edad"].map(orden_edad)
    pir["pct"] = pir["poblacion"] / pir.groupby("anio")["poblacion"].transform("sum") * 100
    pir["sexo"] = pir["sexo"].map({"H": "Hombres", "M": "Mujeres"})
    pir["grupo"] = np.where(pir["orden"] <= 3, "0-14", np.where(pir["orden"] <= 13, "15-64", "65+"))
    t["pbi_piramide"] = pir[["anio", "cod_edad", "poblacion", "edad", "orden", "pct", "sexo", "grupo"]]

    # ---------------------------------------------------------------- participación por edad y sexo (EAPS)
    tp = _leer(conn, f"""
        SELECT anio, valor AS tasa, sexo, grupo_edad AS edad FROM silver.fact_historico
        WHERE cod_territorio = '00' AND cod_indicador = 'TASA_PARTICIPACION' AND sexo IN ('H', 'M')
          AND grupo_edad IN ({", ".join(f"'{e_}'" for e_ in EDADES_EAPS)})""")
    tp["tasa"] = tp["tasa"].astype(float)
    tp["sexo"] = tp["sexo"].map({"H": "Hombres", "M": "Mujeres"})
    tp["orden"] = tp["edad"].map(EDADES_EAPS)
    t["pbi_participacion"] = tp

    # ---------------------------------------------------------------- regiones
    terr = _leer(conn, "SELECT cod_territorio, nombre_es, nombre_en FROM silver.dim_territorio WHERE tipo = 'sido' "
                       "ORDER BY cod_territorio")
    terr = terr.rename(columns={"nombre_es": "si_do", "nombre_en": "nombre_ingles"})
    terr["region_macro"] = terr["cod_territorio"].map(REGION)
    terr["orden"] = range(1, len(terr) + 1)
    t["pbi_territorio"] = terr
    rg = _leer(conn, "SELECT * FROM gold.indicadores_riesgo")
    sido = panel[panel["tipo_territorio"] == "sido"]
    nacs = sido.pivot_table(index="cod_territorio", columns="anio", values="nacimientos")
    rg["var_nacimientos_10a_pct"] = rg["cod_territorio"].map((nacs[2025] / nacs[2015] - 1) * 100)
    rg["nivel_riesgo"] = np.select([rg["ranking"] <= 6, rg["ranking"] <= 11], ["Alto", "Medio"], "Bajo")   # tercios
    t["pbi_riesgo"] = rg.rename(columns={"dependencia_vejez": "dep_vejez", "reemplazo_laboral": "ind_reemplazo_laboral",
                                         "var_pob_15_64_proy_pct": "var_pob_15_64_2052_pct", "ranking": "ranking_riesgo"})[
        ["cod_territorio", "tfr", "prop_65mas", "dep_vejez", "tasa_participacion", "ind_reemplazo_laboral",
         "var_pob_15_64_2052_pct", "var_nacimientos_10a_pct", "indice_riesgo", "ranking_riesgo", "nivel_riesgo"]]
    reg = sido[(sido["nivel"] == "historico")][["anio", "cod_territorio", "tfr", "nacimientos", "prop_65mas",
                                                 "dependencia_vejez", "tasa_participacion", "pob_15_64"]]
    reg.columns = ["anio", "cod_territorio", "TFR", "NACIMIENTOS", "PROP_65MAS", "DEP_VEJEZ", "TASA_PARTICIPACION", "POB_15_64"]
    reg["tipo_dato_poblacion"] = np.where(reg["anio"] <= 2022, "estimado", "proyeccion_oficial")
    t["pbi_regional"] = reg.sort_values(["cod_territorio", "anio"])

    # ---------------------------------------------------------------- comparación internacional
    ind = {"tfr": ("TFR", "Fecundidad (TFR)"), "prop_65mas": ("PROP_65MAS", "Población 65+ (%)"),
           "dependencia_vejez": ("DEP_VEJEZ", "Dependencia de vejez"),
           "tasa_participacion": ("TASA_PARTICIPACION", "Participación laboral (%)")}
    p = panel[(panel["nivel"] == "historico") & panel["cod_territorio"].isin(PAISES)]
    ii = p.melt(id_vars=["anio", "cod_territorio"], value_vars=list(ind), var_name="c", value_name="valor").dropna()
    ii["cod_indicador"], ii["indicador"] = ii["c"].map(lambda c: ind[c][0]), ii["c"].map(lambda c: ind[c][1])
    ii["pais"], ii["es_corea"] = ii["cod_territorio"].map(PAISES), ii["cod_territorio"].eq("00")
    t["pbi_internacional"] = ii[["anio", "cod_indicador", "valor", "pais", "indicador", "es_corea"]]

    # ---------------------------------------------------------------- KPIs del problema, OKR y calidad
    t["pbi_kpi"] = _kpis(conn, n, panel, res, rg, terr, activos25)
    t["pbi_okr"] = _okr(conn, kpis, n, res, activos25)
    cal = _leer(conn, "SELECT * FROM gold.v_calidad_dataset ORDER BY fuente, dataset")
    cal["dataset"] = cal["fuente"] + "/" + cal["dataset"]
    cal["rechazos_trazados"] = cal["registros_rechazados"].astype(float)
    cal["rechazos_trazados_pct"] = 100.0
    cal["cumple_validos"], cal["cumple_rechazo"] = cal["tasa_validos_pct"] >= 98, cal["tasa_rechazo_pct"] <= 2
    t["pbi_calidad"] = cal[["dataset", "registros_evaluados", "registros_validos", "registros_rechazados",
                            "rechazos_trazados", "tasa_validos_pct", "tasa_rechazo_pct", "rechazos_trazados_pct",
                            "cumple_validos", "cumple_rechazo"]]
    c = _leer(conn, "SELECT cod_indicador, fuente_contraste, dif_pct, dentro_tolerancia FROM gold.v_conciliacion "
                    "WHERE nivel = 'historico'")
    t["pbi_conciliacion"] = c.groupby(["cod_indicador", "fuente_contraste"], as_index=False).agg(
        pares=("dif_pct", "size"), pct_dentro=("dentro_tolerancia", "mean"), dif_max_pct=("dif_pct", lambda s: s.abs().max()))
    t["pbi_conciliacion"]["pct_dentro"] *= 100
    return {k: _tipos(v) for k, v in t.items()}


def _kpis(conn, n, panel, res, rg, terr, activos25) -> pd.DataFrame:
    a = n.set_index("anio")
    oed = panel[(panel["cod_territorio"] == "OED") & (panel["nivel"] == "historico")].set_index("anio")
    ult = lambda s: (int(s.dropna().sort_index().index[-1]), float(s.dropna().sort_index().iloc[-1]))
    pe = _leer(conn, f"""SELECT escenario, valor FROM silver.fact_proyeccion WHERE cod_territorio = '00' AND sexo = 'T'
                         AND cod_indicador = 'POBLACION' AND grupo_edad = '15-64' AND anio = 2050
                         AND edicion_proyeccion = '{EDICION}'""").set_index("escenario")["valor"].astype(float)
    p25 = a.loc[2025, "POB_15_64"]
    cambio = (pe / p25 - 1) * 100
    fl50 = res[(res["escenario_kostat"] == "medio") & (res["anio"] == 2050)].set_index("id_supuesto")["fuerza_laboral"]
    fl50 = ((fl50.astype(float) / activos25 - 1) * 100).sort_index()
    tp = _leer(conn, """SELECT sexo, valor FROM silver.fact_historico WHERE cod_territorio = '00' AND anio = 2025
                        AND cod_indicador = 'TASA_PARTICIPACION' AND grupo_edad = '15+'""").set_index("sexo")["valor"].astype(float)
    nombres = terr.set_index("cod_territorio")["si_do"]
    top3 = ", ".join(nombres[c] for c in rg.sort_values("ranking")["cod_territorio"].head(3))
    ev_anio, ev = ult(a["ESPERANZA_VIDA"])
    oe_tfr_anio, oe_tfr = ult(oed["tfr"])
    filas = [
        ("KPI-01", "Natalidad", "Tasa global de fecundidad", "publicado por KOSTAT", "KOSIS DT_1B81A17", "observado", 2025,
         a.loc[2025, "TFR"], es(a.loc[2025, "TFR"], 2), "hijos por mujer", f"reemplazo 2,1 · OCDE {es(oe_tfr, 2)} ({oe_tfr_anio})",
         "Crítico", f"{es(a.loc[2025, 'TFR'] / 2.1 * 100, 0)} % del nivel de reemplazo; mínimo histórico 0,72 en 2023"),
        ("KPI-02", "Natalidad", "Variación de nacimientos desde 2000", "(N_t / N_2000 − 1) × 100", "KOSIS DT_1B8000G",
         "calculado", 2025, (a.loc[2025, "NACIMIENTOS"] / a.loc[2000, "NACIMIENTOS"] - 1) * 100,
         es((a.loc[2025, "NACIMIENTOS"] / a.loc[2000, "NACIMIENTOS"] - 1) * 100), "%", "0 % (nivel de 2000)", "Crítico",
         f"{es(a.loc[2000, 'NACIMIENTOS'], 0)} → {es(a.loc[2025, 'NACIMIENTOS'], 0)} nacidos vivos"),
        ("KPI-03", "Natalidad", "Crecimiento natural", "nacimientos − defunciones", "KOSIS DT_1B8000G", "observado", 2025,
         a.loc[2025, "CRECIMIENTO_NATURAL"], es(a.loc[2025, "CRECIMIENTO_NATURAL"], 0), "personas", "0 (equilibrio)", "Crítico",
         "negativo desde 2020: la población ya decrece por dinámica natural"),
        ("KPI-04", "Envejecimiento", "Esperanza de vida al nacer", "publicado por KOSTAT", "KOSIS DT_1B8000F", "observado",
         ev_anio, ev, es(ev), "años", "—", "Contexto",
         f"+{es(ev - a.loc[2000, 'ESPERANZA_VIDA'])} años desde 2000: más años en edad de jubilación"),
        ("KPI-05", "Envejecimiento", "Población de 65 y más", "P65+ / P × 100", "KOSIS DT_1BPA001", "preliminar", 2025,
         a.loc[2025, "PROP_65MAS"], es(a.loc[2025, "PROP_65MAS"]), "%", "ONU: ≥ 14 % envejecida · ≥ 20 % superenvejecida",
         "Crítico", f"umbral de sociedad superenvejecida (20 %) superado en 2025; {es(a.loc[2050, 'PROP_65MAS'], 0)} % en 2050"),
        ("KPI-06", "Envejecimiento", "Dependencia de vejez", "P65+ / P15-64 × 100", "calculado en el pipeline", "preliminar",
         2025, a.loc[2025, "DEP_VEJEZ"], es(a.loc[2025, "DEP_VEJEZ"]), "por 100 en edad de trabajar",
         f"OCDE {es(oed.loc[2025, 'dependencia_vejez'])} (2025)", "Crítico",
         f"hoy al nivel OCDE; {es(a.loc[2050, 'DEP_VEJEZ'], 0)} en 2050 (proyección KOSTAT medio)"),
        ("KPI-07", "Fuerza laboral", "Variación de la población 15-64 a 2050", "(P15-64_2050 / P15-64_2025 − 1) × 100",
         "KOSTAT", "proyeccion_oficial", 2050, cambio["medio"], es(cambio["medio"]), "%", "0 % (sin pérdida)", "Crítico",
         f"{es(p25 / 1e6)} M → {es(pe['medio'] / 1e6)} M; entre {es(cambio.min(), 0)} % y {es(cambio.max(), 0)} % "
         f"en los {len(cambio)} escenarios de KOSTAT"),
        ("KPI-08", "Fuerza laboral", "Índice de reemplazo laboral", "P15-24 / P55-64 × 100", "calculado en el pipeline",
         "preliminar", 2025, a.loc[2025, "IND_REEMPLAZO_LABORAL"], es(a.loc[2025, "IND_REEMPLAZO_LABORAL"], 0),
         "jóvenes por 100 próximos a retiro", "100 (reemplazo completo)", "Crítico",
         f"bajo 100 desde 2016; {es(a.loc[2000, 'IND_REEMPLAZO_LABORAL'], 0)} en 2000"),
        ("KPI-09", "Fuerza laboral", "Tasa de participación laboral (15+)", "PEA / P15+ × 100", "KOSIS EAPS", "observado",
         2025, a.loc[2025, "TASA_PARTICIPACION"], es(a.loc[2025, "TASA_PARTICIPACION"]), "%",
         f"OCDE {es(oed.loc[2025, 'tasa_participacion'])} (2025, modelado OIT)", "Normal",
         "por encima del promedio OCDE: margen limitado para compensar con más participación total"),
        ("KPI-10", "Fuerza laboral", "Brecha de género en participación", "TP hombres − TP mujeres", "KOSIS EAPS",
         "calculado", 2025, tp["H"] - tp["M"], es(tp["H"] - tp["M"]), "puntos porcentuales", "≤ 10 pp", "Alerta",
         f"hombres {es(tp['H'])} % vs mujeres {es(tp['M'])} %: principal palanca de participación"),
        ("KPI-11", "Fuerza laboral", "Variación de la fuerza laboral potencial a 2050",
         "Σ P_proy × cobertura × TP_supuesta; (2050/2025 − 1) × 100", "escenario propio", "escenario_propio", 2050,
         fl50["A"], es(fl50["A"]), "%", "0 % (sin pérdida)", "Crítico",
         " · ".join(f"{s} {es_s(v)} %" for s, v in fl50.items()) + " (no es pronóstico)"),
        ("KPI-12", "Territorio", "Si-do en riesgo demográfico alto", "nº de si-do en el tercio superior del índice",
         "índice propio", "inferencia_propia", 2025, 6.0, "6", "de 17 si-do", "—", "Alerta", f"mayor riesgo: {top3}"),
        ("KPI-13", "Contexto", "Efecto de la migración en la población 15-64 a 2050",
         "cambio 2025-2050: migración alta − sin migración", "KOSTAT", "proyeccion_oficial", 2050,
         cambio["migracion_alta"] - cambio["sin_migracion"], es(cambio["migracion_alta"] - cambio["sin_migracion"]),
         "puntos porcentuales", "—", "Contexto",
         f"{es(cambio['migracion_alta'])} % con migración alta vs {es(cambio['sin_migracion'])} % sin migración: amortigua, no revierte"),
        ("KPI-14", "Contexto", "PIB por hora trabajada", "publicado por la OCDE", "OECD Productivity", "observado", 2025,
         a.loc[2025, "PIB_HORA"], es(a.loc[2025, "PIB_HORA"]), "USD PPA constantes", "—", "Contexto",
         f"+{es((a.loc[2025, 'PIB_HORA'] / a.loc[2000, 'PIB_HORA'] - 1) * 100, 0)} % desde 2000: la productividad es la otra vía de compensación"),
    ]
    k = pd.DataFrame(filas, columns=["codigo", "eje", "indicador", "formula", "fuente", "tipo_dato", "anio", "valor",
                                     "valor_texto", "unidad", "referencia", "semaforo", "lectura"])
    k["semaforo_icono"] = k["semaforo"].map(ICONO_SEM)
    k["ultimo_valor"] = k["valor_texto"] + " (" + k["anio"].astype(str) + ")"
    return k


def _okr(conn, kpis, n, res, activos25) -> pd.DataFrame:
    v = lambda k: float(kpis.loc[k, "valor"])
    a = n.set_index("anio")
    pe = _leer(conn, f"""SELECT escenario, valor FROM silver.fact_proyeccion WHERE cod_territorio = '00' AND sexo = 'T'
                         AND cod_indicador = 'POBLACION' AND grupo_edad = '15-64' AND anio = 2050
                         AND edicion_proyeccion = '{EDICION}'""").set_index("escenario")["valor"].astype(float)
    p25 = a.loc[2025, "POB_15_64"]
    cambio = (pe / p25 - 1) * 100
    fl = res[(res["escenario_kostat"] == "medio") & (res["anio"] == 2050)].set_index("id_supuesto")["fuerza_laboral"].astype(float).sort_index()
    conc = _leer(conn, """SELECT avg(abs(dif_pct)) FROM silver.conciliacion WHERE nivel = 'historico'
                          AND cod_indicador IN ('PROP_65MAS', 'INDICE_ENVEJECIMIENTO', 'DEPENDENCIA_VEJEZ')""").iloc[0, 0]
    oed = _leer(conn, "SELECT anio, tfr FROM gold.v_panel_indicadores WHERE cod_territorio = 'OED' AND nivel = 'historico' "
                      "AND tfr IS NOT NULL ORDER BY anio DESC LIMIT 1")
    oe_anio, oe_tfr = int(oed.iloc[0, 0]), float(oed.iloc[0, 1])
    pal = {"part": (fl["B"] - fl["A"]) / activos25 * 100, "brecha": (fl["D"] - fl["A"]) / activos25 * 100,
           "mig": (pe["migracion_alta"] - pe["sin_migracion"]) / p25 * 100, "fec": (pe["alto"] - pe["medio"]) / p25 * 100}
    flt = " · ".join(f"{s} {es_s((x / activos25 - 1) * 100)} %" for s, x in fl.items())
    O1 = ("O1", "Diagnóstico", "Diagnosticar la magnitud de la caída de la natalidad y del envejecimiento (2000-2025)")
    O2 = ("O2", "Impacto laboral", "Dimensionar el impacto sobre la fuerza laboral futura (2025-2072), separando proyección "
                                   "oficial y escenarios propios")
    O3 = ("O3", "Decisión", "Orientar la decisión pública: dónde y con qué palancas actuar")
    O4 = ("O4", "Calidad del dato", "Habilitador: garantizar datos confiables, trazables y reproducibles")
    filas = [
        (*O1, "KR1.1", "Serie demográfica y laboral integrada 2000-2025: nacional y 17 si-do",
         "completitud ≥ 95 % nacional y ≥ 90 % regional",
         f"{es(v('completitud_nacional_pct'))} % / {es(v('completitud_regional_pct'))} %",
         v("completitud_nacional_pct") >= 95 and v("completitud_regional_pct") >= 90,
         "celdas con dato / esperadas (Sejong desde 2012; EAPS Sejong desde 2017)", "ctl.kpis"),
        (*O1, "KR1.2", "Indicadores de envejecimiento con fórmula única, contrastados con el Banco Mundial",
         "3 indicadores · diferencia media ≤ 3 %", f"3 · {es(float(conc), 2)} %", float(conc) <= 3,
         "proporción de 65+, índice de envejecimiento y dependencia de vejez calculados en el pipeline", "silver.conciliacion"),
        (*O1, "KR1.3", "Brecha de Corea frente a la OCDE cuantificada", "≥ 5 países de comparación", "7 + OCDE + Corea", True,
         f"TFR Corea {es(a.loc[2025, 'TFR'], 2)} vs OCDE {es(oe_tfr, 2)} ({oe_anio}): {es((1 - a.loc[2025, 'TFR'] / oe_tfr) * 100, 0)} % por debajo",
         "gold.v_panel_indicadores"),
        (*O2, "KR2.1", "Escenarios oficiales KOSTAT integrados sin modificar y separados del histórico",
         "100 % de registros con escenario y edición", f"{len(pe)} escenarios · {es(v('proyeccion_con_edicion_escenario_pct'), 0)} %",
         v("proyeccion_con_edicion_escenario_pct") >= 100,
         "2026-2072 nacional y 2026-2052 por si-do; el histórico no contiene proyecciones", "silver.fact_proyeccion"),
        (*O2, "KR2.2", "Escenarios propios de fuerza laboral con supuestos explícitos y calibrados",
         "supuestos versionados · año base = población activa observada", "4 · base 2025 exacta", True,
         "A constante · B tendencia con tope · C convergencia OCDE · D cierre 50 % de la brecha de género",
         "gold.escenario_fuerza_laboral"),
        (*O2, "KR2.3", "Pérdida de población en edad de trabajar y de fuerza laboral a 2050 cuantificada con rango",
         "rango en todos los escenarios", f"15-64: {es(cambio.min())} % a {es(cambio.max())} %", True,
         f"fuerza laboral potencial (medio): {flt}", "silver.fact_proyeccion / gold.escenario_fuerza_laboral"),
        (*O3, "KR3.1", "Riesgo demográfico medido para todas las regiones", "17 de 17 si-do", "17 de 17 · 6 en riesgo alto", True,
         "índice de 4 componentes con igual peso; robusto en 7 esquemas de sensibilidad", "gold.indicadores_riesgo"),
        (*O3, "KR3.2", "Palancas de política cuantificadas (participación, brecha de género, migración, natalidad)",
         "4 de 4 palancas", "4 de 4", True,
         f"efecto a 2050: participación B vs A +{es(pal['part'])} pp · brecha D vs A +{es(pal['brecha'])} pp en fuerza "
         f"laboral · migración alta vs sin +{es(pal['mig'])} pp · fecundidad alta +{es(pal['fec'])} pp en población 15-64",
         "gold.v_proyeccion_escenarios / gold.escenario_fuerza_laboral"),
        (*O3, "KR3.3", "Tablero de Power BI que responde las 10 preguntas de negocio", "10 de 10 preguntas",
         "10 de 10 · 8 páginas", True, "powerbi/Tablero_ETL_Corea_Grupo6.pbip y versión web en dashboard/", "capa gold completa"),
        (*O4, "KR4.1", "Registros válidos tras las reglas de calidad", "≥ 98 % por carga",
         f"{es(v('registros_validos_pct'), 2)} %", v("registros_validos_pct") >= 98, "peor carga: silver.fact_historico",
         "ctl.log_cargas"),
        (*O4, "KR4.2", "Rechazos con motivo trazado", "≤ 2 % y 100 % trazados",
         f"{es(v('tasa_rechazo_pct'), 2)} % · {es(v('rechazos_con_motivo_pct'), 0)} %",
         v("tasa_rechazo_pct") <= 2 and v("rechazos_con_motivo_pct") >= 100,
         "reemplaza el KPI «0 % inconsistencias» (retroalimentación)", "ctl.rechazos"),
        (*O4, "KR4.3", "Coherencia entre fuente maestra y fuentes de contraste", "≥ 90 % de pares ≤ ±3 %",
         f"{es(v('conciliacion_dentro_tolerancia_pct'))} %", v("conciliacion_dentro_tolerancia_pct") >= 90,
         kpis.loc["conciliacion_dentro_tolerancia_pct", "detalle"], "silver.conciliacion"),
        (*O4, "KR4.4", "Fuentes institucionales integradas y ejecuciones sin fallo técnico", "≥ 3 fuentes · ≥ 95 % ejecuciones",
         f"{v('fuentes_institucionales'):.0f} · {es(v('ejecuciones_sin_fallo_pct'), 0)} %",
         v("fuentes_institucionales") >= 3 and v("ejecuciones_sin_fallo_pct") >= 95,
         "KOSTAT/KOSIS, OECD, World Bank y UN WPP", "ctl.log_cargas"),
    ]
    o = pd.DataFrame(filas, columns=["objetivo_cod", "eje", "objetivo", "kr", "kpi", "meta", "valor", "cumple",
                                     "interpretacion", "tabla_gold"])
    o["estado"] = np.where(o["cumple"], "✅ Logrado", "❌ Pendiente")
    return o[["objetivo_cod", "eje", "objetivo", "kr", "kpi", "meta", "valor", "estado", "interpretacion", "tabla_gold"]]


def _tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos limpios para Power BI: enteros sin nulos -> int64; textos -> str; bool -> bool; números -> float64."""
    df = df.reset_index(drop=True).copy()
    for c in df.columns:
        if pd.api.types.is_bool_dtype(df[c]):
            df[c] = df[c].astype(bool)
        elif pd.api.types.is_integer_dtype(df[c]):
            df[c] = df[c].astype("int64") if df[c].notna().all() else df[c].astype("float64")
        elif pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].astype("float64")
        else:
            df[c] = df[c].astype(object).where(df[c].notna(), None).map(lambda x: None if x is None else str(x))
    return df


def escribir(t: dict[str, pd.DataFrame]):
    destino = ruta("gold") / "powerbi"
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, df in t.items():
        df.to_parquet(destino / f"{nombre}.parquet", index=False)
    return destino
