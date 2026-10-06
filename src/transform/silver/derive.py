"""Cálculos del pipeline sobre datos ya validados (CLAUDE.md: los derivados no se toman de las fuentes).

- Agregados de edad de POBLACION (0-14, 15-64, 65+) cuando la fuente no los trae.
- Agregado territorial Chungnam + Sejong (CNSJ): suma de niveles y tasas recalculadas desde los niveles.
- Indicadores derivados: PROP_65MAS, INDICE_ENVEJECIMIENTO y DEPENDENCIA_VEJEZ.
- Estado 'preliminar' / 'definitivo'.
"""
import pandas as pd

# En histórico edicion_proyeccion y escenario valen "-" (centinela) para poder agrupar sin perder filas.
GRUPO = ["nivel", "anio", "cod_territorio", "sexo", "edicion_proyeccion", "escenario"]
CONTEXTO = ["fuente", "fecha_extraccion", "version_publicacion"]


def _filas(base: pd.DataFrame, valores: pd.Series, indicador: str, grupo_edad: str, origen=None) -> pd.DataFrame:
    out = base.copy()
    out["cod_indicador"], out["grupo_edad"], out["valor"] = indicador, grupo_edad, valores.values
    out["id_carga_origen"] = origen
    return out


def agregados_edad(df: pd.DataFrame, agregados: dict) -> pd.DataFrame:
    """Suma quinquenales -> 0-14 / 15-64 / 65+ solo si están todos los componentes y la fuente no trae el agregado."""
    pob = df[df["cod_indicador"] == "POBLACION"]
    nuevos = []
    for destino, componentes in agregados.items():
        partes = pob[pob["grupo_edad"].isin(componentes)]
        g = partes.groupby(GRUPO + CONTEXTO + ["id_carga_origen"], dropna=False)["valor"].agg(["sum", "count"]).reset_index()
        g = g[g["count"] == len(componentes)]
        ya = pob[pob["grupo_edad"] == destino].set_index(GRUPO).index
        g = g[~g.set_index(GRUPO).index.isin(ya)]
        nuevos.append(_filas(g[GRUPO + CONTEXTO], g["sum"], "POBLACION", destino, g["id_carga_origen"].values))
    return pd.concat([df, *nuevos], ignore_index=True)


def chungnam_sejong(df: pd.DataFrame, regla: dict) -> pd.DataFrame:
    """CNSJ = Chungnam (34) + Sejong (29). Antes de existir Sejong, Chungnam ya lo incluye: se suma lo disponible."""
    comp = df[df["cod_territorio"].isin(regla["componentes"]) & df["cod_indicador"].isin(regla["indicadores_suma"])]
    k = [c for c in GRUPO if c != "cod_territorio"] + ["grupo_edad", "cod_indicador"]
    g = comp.groupby(k + CONTEXTO, dropna=False, as_index=False)["valor"].sum()
    g["cod_territorio"], g["id_carga_origen"] = regla["codigo"], None
    # Tasas EAPS recalculadas desde los niveles (no se suman tasas).
    lv = g[g["cod_indicador"].isin(["POB_15MAS", "POB_ACTIVA", "OCUPADOS"])].pivot_table(
        index=[c for c in k if c != "cod_indicador"] + ["cod_territorio"] + CONTEXTO, columns="cod_indicador",
        values="valor", dropna=False).dropna(how="all")
    tasas = []
    if {"POB_15MAS", "POB_ACTIVA", "OCUPADOS"} <= set(lv.columns):
        base = lv.reset_index()[lv.index.names]
        tasas += [_filas(base, (lv["POB_ACTIVA"] / lv["POB_15MAS"] * 100).round(1), "TASA_PARTICIPACION", None),
                  _filas(base, ((lv["POB_ACTIVA"] - lv["OCUPADOS"]) / lv["POB_ACTIVA"] * 100).round(1), "TASA_DESEMPLEO", None)]
        for t in tasas:
            t["grupo_edad"] = base["grupo_edad"].values
    return pd.concat([df, g, *tasas], ignore_index=True).dropna(subset=["valor"])


def derivados(df: pd.DataFrame) -> pd.DataFrame:
    """Se alinean las poblaciones por grupo y fuente (no por fecha: en World Bank cada grupo de edad es un
    dataset distinto, extraído con segundos de diferencia). La fecha del derivado es la más reciente."""
    pob = df[(df["cod_indicador"] == "POBLACION") & df["grupo_edad"].isin(["TOTAL", "0-14", "15-64", "65+"])]
    idx = GRUPO + ["fuente"]
    ancho = pob.pivot_table(index=idx, columns="grupo_edad", values="valor", aggfunc="first")
    ctx = pob.groupby(idx).agg(fecha_extraccion=("fecha_extraccion", "max"), version_publicacion=("version_publicacion", "first"))
    ancho = ancho.join(ctx)
    base = ancho.reset_index()[GRUPO + CONTEXTO]
    calcs = {"PROP_65MAS": ("65+", "TOTAL"), "INDICE_ENVEJECIMIENTO": ("65+", "0-14"), "DEPENDENCIA_VEJEZ": ("65+", "15-64")}
    nuevos = [_filas(base, ancho[num] / ancho[den] * 100, ind, "TOTAL")
              for ind, (num, den) in calcs.items() if num in ancho and den in ancho]
    return pd.concat([df, *nuevos], ignore_index=True).dropna(subset=["valor"])


def estado(df: pd.DataFrame, regla: dict) -> pd.Series:
    """'preliminar': último año publicado (histórico) y población KOSIS que en realidad es proyectada."""
    hist = df["nivel"] == "historico"
    ultimo = hist & (df["anio"] == regla["ultimo_anio"])
    p = regla["poblacion_proyectada_kosis"]
    proyectada = (hist & (df["fuente"] == "KOSIS") & df["cod_indicador"].isin(
        ["POBLACION", "PROP_65MAS", "INDICE_ENVEJECIMIENTO", "DEPENDENCIA_VEJEZ"]) & df["anio"].between(p["desde"], p["hasta"]))
    return (ultimo | proyectada).map({True: "preliminar", False: "definitivo"})
