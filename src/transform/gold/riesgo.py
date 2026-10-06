"""Pregunta 5: índice de riesgo demográfico por si-do (descriptivo, no causal).

Cada componente se normaliza 0-100 entre los 17 si-do (100 = más riesgo según su dirección en config.yaml) y el
índice es el promedio ponderado. Así el ranking es transparente: se puede ver qué componente lo explica.

La normalización base es min-max. Como un valor extremo (Sejong, el único si-do que crece) estira la escala y
comprime al resto, la sensibilidad también recalcula el ranking con percentiles (solo importa el orden).
"""
import pandas as pd


def calcular(hist: pd.DataFrame, proy: pd.DataFrame, dims: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    r = cfg["gold"]["riesgo_sido"]
    base, futuro = r["anio_base"], r["anio_proyeccion"]
    sidos = dims.loc[dims["tipo"] == "sido", "cod_territorio"]

    def valor(df, indicador, anio, edad="TOTAL"):
        d = df[df["cod_territorio"].isin(sidos) & (df["sexo"] == "T") & (df["cod_indicador"] == indicador) &
               (df["grupo_edad"] == edad) & (df["anio"] == anio)]
        return d.set_index("cod_territorio")["valor"]

    p_sido = proy[(proy["edicion_proyeccion"] == cfg["silver"]["ediciones"]["kosis_sido"]) & (proy["escenario"] == "medio")]
    pob_1564 = valor(hist, "POBLACION", base, "15-64")
    t = pd.DataFrame({
        "prop_65mas": valor(hist, "PROP_65MAS", base),
        "tfr": valor(hist, "TFR", base),
        "dependencia_vejez": valor(hist, "DEPENDENCIA_VEJEZ", base),
        "indice_envejecimiento": valor(hist, "INDICE_ENVEJECIMIENTO", base),
        "tasa_participacion": valor(hist, "TASA_PARTICIPACION", base, "15+"),
        "var_pob_15_64_hist_pct": (pob_1564 / valor(hist, "POBLACION", 2015, "15-64") - 1) * 100,
        "var_pob_15_64_proy_pct": (valor(p_sido, "POBLACION", futuro, "15-64") / pob_1564 - 1) * 100,
        "dependencia_vejez_proy": valor(p_sido, "DEPENDENCIA_VEJEZ", futuro),
        # reemplazo laboral: jóvenes que entran (15-24) por cada 100 que se acercan al retiro (55-64)
        "reemplazo_laboral": ((valor(hist, "POBLACION", base, "15-19") + valor(hist, "POBLACION", base, "20-24")) /
                              (valor(hist, "POBLACION", base, "55-59") + valor(hist, "POBLACION", base, "60-64")) * 100),
    })
    t["indice_riesgo"] = indice(t, r["componentes"])
    t["ranking"] = t["indice_riesgo"].rank(ascending=False, method="min").astype(int)
    t["anio_base"], t["anio_proyeccion"] = base, futuro
    return t.reset_index(names="cod_territorio").sort_values("ranking")


def indice(t: pd.DataFrame, componentes: dict, normalizacion: str = "minmax") -> pd.Series:
    puntajes, pesos = [], 0
    for comp, regla in componentes.items():
        x = t[comp]
        if normalizacion == "percentil":
            norm = (x.rank() - 1) / (x.count() - 1) * 100
        elif normalizacion == "zscore":   # puntaje estándar (no queda en 0-100; sirve para comparar el orden)
            norm = (x - x.mean()) / x.std(ddof=0)
            puntajes.append((norm if regla["mas_es_peor"] else -norm) * regla["peso"])
            pesos += regla["peso"]
            continue
        else:
            norm = (x - x.min()) / (x.max() - x.min()) * 100
        puntajes.append((norm if regla["mas_es_peor"] else 100 - norm) * regla["peso"])
        pesos += regla["peso"]
    return sum(puntajes) / pesos


def sensibilidad(t: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Ranking con esquemas de pesos alternativos (config.yaml). Si los primeros puestos se mantienen, el
    resultado no depende de la elección de pesos ni del método de normalización."""
    r = cfg["gold"]["riesgo_sido"]
    base = r["componentes"]
    direccion = {**{c: v["mas_es_peor"] for c, v in base.items()},
                 **{c: v["mas_es_peor"] for c, v in r.get("componentes_extra", {}).items()}}
    t = t.set_index("cod_territorio")
    pesos_base = {c: v["peso"] for c, v in base.items()}
    sin_norm = lambda p: {c: w for c, w in p.items() if c != "normalizacion"}
    esquemas = {"base": (pesos_base, "minmax"),
                **{e: (sin_norm(p), p.get("normalizacion", "minmax")) for e, p in r["esquemas_sensibilidad"].items()},
                **{f"base_normalizacion_{n}": (pesos_base, n) for n in r.get("normalizaciones_sensibilidad", [])}}
    filas = []
    for esquema, (pesos, normalizacion) in esquemas.items():
        comps = {c: {"peso": w, "mas_es_peor": direccion[c]} for c, w in pesos.items() if w}
        idx = indice(t, comps, normalizacion)
        filas.append(pd.DataFrame({"cod_territorio": idx.index, "esquema": esquema, "indice_riesgo": idx.values,
                                   "ranking": idx.rank(ascending=False, method="min").astype(int).values}))
    return pd.concat(filas, ignore_index=True)
