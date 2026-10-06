"""Reglas de validación bronze -> silver. Cada registro que falla va a ctl.rechazos con su regla y motivo.

Reglas (CLAUDE.md, sección 5): tipo y nulos, rango por indicador, indicador válido, clave única y coherencia de
totales (suma de grupos de edad ≈ total y hombres + mujeres ≈ total en población y EAPS, con la tolerancia y el
redondeo de cada fuente definidos en config.yaml).
"""
import pandas as pd

from src.transform.silver.homologacion import rechazos

CLAVE_HIST = ["anio", "cod_territorio", "sexo", "grupo_edad", "cod_indicador"]
CLAVE_PROY = CLAVE_HIST + ["edicion_proyeccion", "escenario"]


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


def _incoherentes(partes: pd.Series, total: pd.Series, tolerancia_pct: float, margen: float) -> pd.Series:
    """Diferencia % de las filas que superan la tolerancia Y el margen de redondeo de la fuente."""
    dif = (partes - total).abs()
    pct = dif / total.abs() * 100
    return pct[(pct > tolerancia_pct) & (dif > margen)].dropna()


def coherencia_totales(df: pd.DataFrame, tolerancia_pct: float, reglas: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Por indicador de nivel (config.yaml, calidad.coherencia_totales): suma de grupos de edad ≈ total y
    H + M ≈ T. Margen de redondeo = medio redondeo por componente sumado. Si no cuadra, se rechaza la fila del total."""
    k = ["nivel", "anio", "cod_territorio", "edicion_proyeccion", "escenario", "fuente"]
    malas = []
    for ind, r in reglas.items():
        d = df[df["cod_indicador"] == ind]
        suma = d[d["grupo_edad"].isin(r["grupos"])].groupby(k + ["sexo"], dropna=False)["valor"].agg(["sum", "count"])
        tot = d[d["grupo_edad"] == r["total"]].set_index(k + ["sexo"])["valor"]
        comp = suma.join(tot.rename("total"), how="inner")
        comp = comp[comp["count"] == len(r["grupos"])]
        dif = _incoherentes(comp["sum"], comp["total"], tolerancia_pct, r["redondeo"] * len(r["grupos"]) / 2)
        for idx, v in dif.items():
            malas.append((ind, dict(zip(k + ["sexo"], idx)), r["total"], f"suma de edades difiere {v:.2f}% del total"))

        porsexo = d.pivot_table(index=k + ["grupo_edad"], columns="sexo", values="valor", aggfunc="first", dropna=False)
        if {"T", "H", "M"} <= set(porsexo.columns):
            dif = _incoherentes(porsexo["H"] + porsexo["M"], porsexo["T"], tolerancia_pct, r["redondeo"])
            for idx, v in dif.items():
                claves = dict(zip(k + ["grupo_edad"], idx))
                malas.append((ind, {**claves, "sexo": "T"}, claves["grupo_edad"], f"H + M difiere {v:.2f}% del total"))

    if not malas:
        return df, rechazos(df.iloc[0:0], "", "")
    mascara = pd.Series(False, index=df.index)
    motivos = {}
    for ind, claves, edad, motivo in malas:
        m = (df["cod_indicador"] == ind) & (df["grupo_edad"] == edad)
        for c, v in claves.items():
            if c != "grupo_edad":
                m &= df[c].isna() if pd.isna(v) else df[c] == v
        mascara |= m
        motivos.update({i: motivo for i in df.index[m]})
    rech = rechazos(df[mascara], "coherencia_totales", lambda r: motivos[r.Index])
    return df[~mascara], rech
