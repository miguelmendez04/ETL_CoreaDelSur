"""Conciliación maestra vs contraste -> silver.conciliacion. El contraste nunca reemplaza el valor maestro.

Solo Corea, nivel nacional y sexo total, con definiciones comparables (la dependencia de vejez de la OECD es
65+/20-64 y no entra). Los filtros de OECD salen del perfilamiento (notebook 02): sin ellos se mezclan series.
"""
import pandas as pd

from src.transform.silver.desde_bronze import DatasetBronze

COLS = ["nivel", "anio", "grupo_edad", "cod_indicador", "escenario", "fuente_contraste", "valor_contraste"]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def contraste_worldbank(wb: dict[str, DatasetBronze]) -> pd.DataFrame:
    def serie(codigo):
        r = wb[codigo].registros
        r = r[r["countryiso3code"] == "KOR"]
        return pd.Series(_num(r["value"]).values, index=r["date"].astype(int).values)

    directos = {"SP.DYN.TFRT.IN": ("TFR", "TOTAL"), "SP.POP.TOTL": ("POBLACION", "TOTAL"),
                "SP.POP.0014.TO": ("POBLACION", "0-14"), "SP.POP.1564.TO": ("POBLACION", "15-64"),
                "SP.POP.65UP.TO": ("POBLACION", "65+"), "SL.TLF.CACT.ZS": ("TASA_PARTICIPACION", "15+"),
                "SP.POP.DPND.OL": ("DEPENDENCIA_VEJEZ", "TOTAL"), "SP.POP.65UP.TO.ZS": ("PROP_65MAS", "TOTAL")}
    series = {(ind, edad): serie(cod) for cod, (ind, edad) in directos.items()}
    # Calculados con datos WB: nacimientos = tasa bruta × población / 1000; envejecimiento = 65+ / 0-14 × 100.
    series[("NACIMIENTOS", "TOTAL")] = serie("SP.DYN.CBRT.IN") * serie("SP.POP.TOTL") / 1000
    series[("INDICE_ENVEJECIMIENTO", "TOTAL")] = serie("SP.POP.65UP.TO") / serie("SP.POP.0014.TO") * 100
    filas = [pd.DataFrame({"anio": s.index, "valor_contraste": s.values, "cod_indicador": ind, "grupo_edad": edad})
             for (ind, edad), s in series.items()]
    return pd.concat(filas).assign(nivel="historico", escenario="NA", fuente_contraste="WB")[COLS]


def contraste_oecd(fecundidad: DatasetBronze, fuerza: DatasetBronze) -> pd.DataFrame:
    f = fecundidad.registros
    f = f[(f["REF_AREA"] == "KOR") & (f["TERRITORIAL_LEVEL"] == "CTRY")]
    tfr = f[(f["MEASURE"] == "FERT_RATIO") & (f["AGE"] == "_T")]
    nac = f[(f["MEASURE"] == "LIVE_BIRTHS") & (f["UNIT_MEASURE"] == "BR")]
    l = fuerza.registros
    l = l[(l["REF_AREA"] == "KOR") & (l["SEX"] == "_T") & (l["AGE"] == "Y_GE15")]
    niveles = l[(l["UNIT_MEASURE"] == "PS") & (l["WORKER_STATUS"] == "_Z") & (l["ACTIVITY"] == "_Z")]
    escala = 10 ** _num(niveles["UNIT_MULT"])          # PS viene en miles (UNIT_MULT=3)
    partes = [
        (tfr, _num(tfr["OBS_VALUE"]), "TFR", "TOTAL"),
        (nac, _num(nac["OBS_VALUE"]), "NACIMIENTOS", "TOTAL"),
        (niveles[niveles["MEASURE"] == "LF"], _num(niveles["OBS_VALUE"]) * escala, "POB_ACTIVA", "15+"),
        (niveles[niveles["MEASURE"] == "EMP"], _num(niveles["OBS_VALUE"]) * escala, "OCUPADOS", "15+"),
        (l[(l["MEASURE"] == "UNE_LF") & (l["UNIT_MEASURE"] == "PT_LF_SUB")], None, "TASA_DESEMPLEO", "15+"),
    ]
    filas = []
    for df, valores, ind, edad in partes:
        v = _num(df["OBS_VALUE"]) if valores is None else valores[df.index]
        filas.append(pd.DataFrame({"anio": df["TIME_PERIOD"].str[:4].astype(int).values, "valor_contraste": v.values,
                                   "cod_indicador": ind, "grupo_edad": edad}))
    return pd.concat(filas).assign(nivel="historico", escenario="NA", fuente_contraste="OECD")[COLS]


def contraste_unwpp(un: DatasetBronze, variantes: dict, hasta_historico: int, agregados: dict) -> pd.DataFrame:
    """Población total y por grandes grupos, ambos sexos. Histórico: variante mediana; proyección: por escenario."""
    r = un.registros
    r = r[(r["sex"] == "Both sexes") & r["variant"].isin(variantes)]
    r = r.assign(anio=r["timeLabel"].astype(int), valor=_num(r["value"]), escenario=r["variant"].map(variantes))
    grupos = {"TOTAL": None, **agregados}
    agregados_fino = {"0-14": ["0-4", "5-9", "10-14"], "65+": ["65-69", "70-74", "75-79", "80-84", "85-89", "90-94", "95-99", "100+"]}
    agregados_fino["15-64"] = [f"{a}-{a + 4}" for a in range(15, 65, 5)]
    filas = []
    for grupo in grupos:
        sub = r if grupo == "TOTAL" else r[r["ageLabel"].isin(agregados_fino[grupo])]
        s = sub.groupby(["escenario", "anio"])["valor"].sum().reset_index()
        filas.append(s.assign(grupo_edad=grupo))
    out = pd.concat(filas).rename(columns={"valor": "valor_contraste"})
    out["nivel"] = out["anio"].map(lambda a: "historico" if a <= hasta_historico else "proyeccion")
    out = out[(out["nivel"] == "proyeccion") | (out["escenario"] == "medio")]
    out.loc[out["nivel"] == "historico", "escenario"] = "NA"
    return out.assign(cod_indicador="POBLACION", fuente_contraste="UNWPP")[COLS]


def conciliar(silver: pd.DataFrame, contrastes: pd.DataFrame) -> pd.DataFrame:
    """Une el valor maestro (Corea nacional, sexo total) con cada contraste disponible para el mismo año y grupo."""
    m = silver[(silver["cod_territorio"] == "00") & (silver["sexo"] == "T")].copy()
    m["escenario"] = m["escenario"].replace("-", "NA")
    m = m[(m["nivel"] == "historico") | (m["edicion_proyeccion"] == "KOSTAT_2022_2072")]
    m = m[["nivel", "anio", "grupo_edad", "cod_indicador", "escenario", "fuente", "valor"]].rename(
        columns={"fuente": "fuente_maestra", "valor": "valor_maestra"})
    out = m.merge(contrastes.dropna(subset=["valor_contraste"]), on=["nivel", "anio", "grupo_edad", "cod_indicador", "escenario"])
    out["cod_territorio"], out["sexo"] = "00", "T"
    out["dif_pct"] = (out["valor_contraste"] - out["valor_maestra"]) / out["valor_maestra"].abs() * 100
    return out
