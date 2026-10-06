"""Preguntas 7 y 8: asociación envejecimiento-empleo-productividad y señales tempranas de escasez laboral.

- Asociación (7): correlación de Pearson 2000-2025 en niveles y en variaciones anuales. Las series con tendencia
  casi siempre correlacionan en niveles; la correlación de las variaciones es la que indica si se mueven juntas
  año a año. Es asociación, no causalidad.
- Hitos de escasez (8): años en que se cruzan umbrales (pico de la población 15-64, relevo generacional < 100,
  dependencia de vejez sobre los umbrales de config.yaml) y caída de la fuerza laboral potencial por escenario.
"""
import pandas as pd


def _serie(df: pd.DataFrame, indicador: str, edad: str, territorio: str = "00") -> pd.Series:
    d = df[(df["cod_territorio"] == territorio) & (df["sexo"] == "T") & (df["cod_indicador"] == indicador) &
           (df["grupo_edad"] == edad)]
    return d.set_index("anio")["valor"].sort_index()


def asociaciones(hist: pd.DataFrame, pares: list[list[str]]) -> pd.DataFrame:
    edad = {"TASA_PARTICIPACION": "15+", "OCUPADOS": "15+", "TASA_DESEMPLEO": "15+", "POB_ACTIVA": "15+"}
    filas = []
    for x, y in pares:
        df = pd.concat({"x": _serie(hist, x, edad.get(x, "TOTAL")), "y": _serie(hist, y, edad.get(y, "TOTAL"))}, axis=1).dropna()
        dif = df.diff().dropna()
        filas.append({"variable_x": x, "variable_y": y, "anio_inicio": int(df.index.min()), "anio_fin": int(df.index.max()),
                      "n": len(df), "corr_niveles": df["x"].corr(df["y"]), "corr_variaciones": dif["x"].corr(dif["y"])})
    return pd.DataFrame(filas)


def _primer_anio(s: pd.Series, condicion) -> int | None:
    a = s[condicion(s)]
    return int(a.index.min()) if not a.empty else None


def hitos(hist: pd.DataFrame, proy: pd.DataFrame, esc: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    edicion = cfg["silver"]["ediciones"]["kosis_nacional"]
    anio_base = cfg["gold"]["escenarios_fuerza_laboral"]["anio_base"]
    p_nac = proy[proy["edicion_proyeccion"] == edicion]
    filas = []

    for escenario in ("medio", "alto", "bajo"):
        p = p_nac[p_nac["escenario"] == escenario]
        pob = pd.concat([_serie(hist, "POBLACION", "15-64"), _serie(p, "POBLACION", "15-64")])
        filas.append({"hito": "pico_poblacion_15_64", "escenario_kostat": escenario, "anio": int(pob.idxmax()),
                      "valor": pob.max(), "descripcion": "Año de máxima población en edad de trabajar (15-64)"})
        relevo = (pd.concat([_serie(hist, "POBLACION", "15-19"), _serie(p, "POBLACION", "15-19")]) /
                  pd.concat([_serie(hist, "POBLACION", "60-64"), _serie(p, "POBLACION", "60-64")]) * 100)
        a = _primer_anio(relevo, lambda s: s < 100)
        filas.append({"hito": "relevo_generacional_bajo_100", "escenario_kostat": escenario, "anio": a,
                      "valor": relevo.get(a), "descripcion": "Primer año con menos personas de 15-19 que de 60-64 (relevo < 100)"})
        filas.append({"hito": "relevo_generacional_minimo", "escenario_kostat": escenario, "anio": int(relevo.idxmin()),
                      "valor": relevo.min(), "descripcion": "Mínimo del relevo generacional (15-19 por cada 100 de 60-64)"})
        dep = pd.concat([_serie(hist, "DEPENDENCIA_VEJEZ", "TOTAL"), _serie(p, "DEPENDENCIA_VEJEZ", "TOTAL")])
        for umbral in cfg["gold"]["senales_escasez"]["umbrales_dependencia"]:
            a = _primer_anio(dep, lambda s: s >= umbral)
            filas.append({"hito": f"dependencia_vejez_supera_{umbral}", "escenario_kostat": escenario, "anio": a,
                          "valor": dep.get(a), "descripcion": f"Primer año con {umbral}+ personas de 65+ por cada 100 de 15-64"})

    activos = _serie(hist, "POB_ACTIVA", "15+")[anio_base]
    tot = esc.groupby(["escenario_kostat", "id_supuesto", "anio"])["fuerza_laboral"].sum()
    for (escenario, sup), s in tot.groupby(level=[0, 1]):
        s = s.droplevel([0, 1])
        filas.append({"hito": "pico_fuerza_laboral", "escenario_kostat": escenario, "id_supuesto": sup,
                      "anio": int(s.idxmax()), "valor": s.max(), "descripcion": "Año de máxima fuerza laboral potencial"})
        for anio in cfg["gold"]["senales_escasez"]["anios_comparacion"]:
            filas.append({"hito": f"cambio_fuerza_laboral_{anio_base}_{anio}_pct", "escenario_kostat": escenario,
                          "id_supuesto": sup, "anio": anio, "valor": (s[anio] / activos - 1) * 100,
                          "descripcion": f"Cambio % de la fuerza laboral potencial respecto a la población activa observada en {anio_base}"})
    out = pd.DataFrame(filas)
    out["anio"] = out["anio"].astype("Int64")   # NULL si el umbral no se cruza en el horizonte
    return out
