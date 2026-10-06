"""Reglas de validación bronze -> silver. Cada registro que falla va a ctl.rechazos con su regla y motivo.

Reglas (CLAUDE.md, sección 5): tipo y nulos, rango por indicador, indicador válido, clave única y coherencia de
totales (suma de grupos de edad ≈ total y hombres + mujeres ≈ total, con tolerancia de config.yaml).
"""
import pandas as pd

from src.transform.silver.homologacion import rechazos

CLAVE_HIST = ["anio", "cod_territorio", "sexo", "grupo_edad", "cod_indicador"]
CLAVE_PROY = CLAVE_HIST + ["edicion_proyeccion", "escenario"]
QUINQUENALES = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
                "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85+"]


def clave(df: pd.DataFrame) -> list[str]:
    return CLAVE_PROY if (df["nivel"] == "proyeccion").any() else CLAVE_HIST


def convertir_valores(df: pd.DataFrame, dims: dict) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Texto -> número × factor. Vacío o '-' es nulo; si el territorio aún no existía ese año no es un rechazo
    sino 'no aplica' (p. ej. Sejong antes de 2012), y solo se cuenta."""
    txt = df["valor_txt"].astype(object).where(df["valor_txt"].notna(), None)
    txt = txt.map(lambda v: None if v is None else str(v).strip())
    vacio = txt.isna() | txt.isin(["", "-", "nan", "None"])
    num = pd.to_numeric(txt.where(~vacio), errors="coerce")
    tipo_invalido = ~vacio & num.isna()

    desde = dims["territorio"].set_index("cod_territorio")["vigente_desde"].replace("", None).dropna().astype(int)
    no_vigente = df["cod_territorio"].map(desde).fillna(0) > df["anio"]
    no_aplica = vacio & no_vigente
    nulo = vacio & ~no_vigente

    rech = pd.concat([
        rechazos(df[nulo], "nulo", lambda r: f"valor vacío ('{r.valor_txt}') en {r.dataset} {r.anio} {r.territorio_src}"),
        rechazos(df[tipo_invalido], "tipo_invalido", lambda r: f"valor no numérico '{r.valor_txt}'"),
    ], ignore_index=True)
    ok = df[~(vacio | tipo_invalido)].copy()
    ok["valor"] = num[ok.index] * ok["factor"].astype(float)
    return ok.drop(columns=["valor_txt"]), rech, int(no_aplica.sum())


def agrupar_edades(df: pd.DataFrame) -> pd.DataFrame:
    """Suma los grupos finos que comparten grupo_edad (85-89 ... 100+ -> 85+). El resto queda igual."""
    k = [c for c in df.columns if c not in ("valor", "id_bronze", "edad_src", "valor_txt")]
    dup = df.duplicated(subset=k + ["grupo_edad"], keep=False) & (df["grupo_edad"] == "85+")
    if not dup.any():
        return df
    sumados = (df[dup].groupby(k, dropna=False, as_index=False)
               .agg(valor=("valor", "sum"), id_bronze=("id_bronze", "min"), edad_src=("edad_src", lambda s: "+".join(s))))
    return pd.concat([df[~dup], sumados], ignore_index=True)


def validar(df: pd.DataFrame, dims: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    ind = dims["indicador"].set_index("cod_indicador")
    invalido = ~df["cod_indicador"].isin(ind.index)
    rmin = df["cod_indicador"].map(pd.to_numeric(ind["rango_min"], errors="coerce"))
    rmax = df["cod_indicador"].map(pd.to_numeric(ind["rango_max"], errors="coerce"))
    fuera = ~invalido & ((df["valor"] < rmin) | (df["valor"] > rmax))
    dup = pd.Series(False, index=df.index)
    for nivel, grupo in df[~invalido & ~fuera].groupby("nivel"):
        dup[grupo.index] = grupo.duplicated(subset=CLAVE_PROY if nivel == "proyeccion" else CLAVE_HIST, keep="first")

    rech = pd.concat([
        rechazos(df[invalido], "indicador_invalido", lambda r: f"indicador '{r.cod_indicador}' no está en dim_indicador"),
        rechazos(df[fuera], "rango", lambda r: f"{r.cod_indicador}={r.valor} fuera de rango"),
        rechazos(df[dup], "clave_duplicada", lambda r: f"clave repetida ({r.anio}, {r.cod_territorio}, {r.sexo}, {r.grupo_edad}, {r.cod_indicador})"),
    ], ignore_index=True)
    return df[~(invalido | fuera | dup)], rech


def coherencia_totales(df: pd.DataFrame, tolerancia_pct: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """POBLACION: suma de quinquenales ≈ TOTAL y H + M ≈ T. Si no cuadra, se rechaza la fila del total."""
    pob = df[df["cod_indicador"] == "POBLACION"]
    k = ["nivel", "anio", "cod_territorio", "edicion_proyeccion", "escenario"]
    malas = []

    suma = (pob[pob["grupo_edad"].isin(QUINQUENALES)].groupby(k + ["sexo"], dropna=False)["valor"].agg(["sum", "count"]))
    tot = pob[pob["grupo_edad"] == "TOTAL"].set_index(k + ["sexo"])["valor"]
    comp = suma.join(tot.rename("total"), how="inner")
    comp = comp[comp["count"] == len(QUINQUENALES)]
    dif = (comp["sum"] - comp["total"]).abs() / comp["total"] * 100
    for idx in dif[dif > tolerancia_pct].index:
        malas.append((dict(zip(k + ["sexo"], idx)), "TOTAL", f"suma de edades difiere {dif[idx]:.2f}% del total"))

    porsexo = pob.pivot_table(index=k + ["grupo_edad"], columns="sexo", values="valor", aggfunc="first", dropna=False)
    if {"T", "H", "M"} <= set(porsexo.columns):
        d = ((porsexo["H"] + porsexo["M"] - porsexo["T"]).abs() / porsexo["T"] * 100).dropna()
        for idx in d[d > tolerancia_pct].index:
            claves = dict(zip(k + ["grupo_edad"], idx))
            malas.append(({**claves, "sexo": "T"}, claves["grupo_edad"], f"H + M difiere {d[idx]:.2f}% del total"))

    if not malas:
        return df, rechazos(df.iloc[0:0], "", "")
    mascara = pd.Series(False, index=df.index)
    motivos = {}
    for claves, edad, motivo in malas:
        m = (df["cod_indicador"] == "POBLACION") & (df["grupo_edad"] == edad)
        for c, v in claves.items():
            if c != "grupo_edad":
                m &= df[c].isna() if pd.isna(v) else df[c] == v
        mascara |= m
        motivos.update({i: motivo for i in df.index[m]})
    rech = rechazos(df[mascara], "coherencia_totales", lambda r: motivos[r.Index])
    return df[~mascara], rech
