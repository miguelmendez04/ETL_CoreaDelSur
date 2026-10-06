"""Pregunta 6b: fuerza laboral potencial bajo supuestos (escenarios A/B/C/D del equipo, no pronósticos).

fuerza_laboral(año, escenario KOSTAT, supuesto, sexo, grupo) = población proyectada × factor_cobertura × tasa / 100

- factor_cobertura: población 15+ de la EAPS / población KOSTAT del mismo sexo y grupo en el año base (la EAPS no
  cubre militares ni población institucional). Con él, el año base reproduce la población activa observada.

- Población: silver.fact_proyeccion, edición nacional KOSTAT_2022_2072 (medio/alto/bajo), quinquenales sumados a
  los grupos de la EAPS (15-19, 20-29, ..., 60+).
- Tasa base: EAPS nacional por sexo y grupo de edad (silver.fact_historico), año base de config.yaml.
- A: constante. B: tendencia lineal 2015-2025 con cambio máximo, piso, tope y año de congelamiento.
  C: convergencia lineal al promedio OCDE por sexo y edad (silver, territorio OED); 15-19 y 60+ constantes.
  D: las mujeres cierran linealmente una fracción de su brecha de participación con los hombres hasta el año meta.
"""
import numpy as np
import pandas as pd


def tasas_eaps(hist: pd.DataFrame, grupos: list[str]) -> pd.DataFrame:
    t = hist[(hist["cod_territorio"] == "00") & hist["sexo"].isin(["H", "M"]) &
             (hist["cod_indicador"] == "TASA_PARTICIPACION") & hist["grupo_edad"].isin(grupos)]
    return t[["anio", "sexo", "grupo_edad", "valor"]].rename(columns={"valor": "tasa"})


def poblacion_grupos(proy: pd.DataFrame, grupos: dict[str, list[str]], edicion: str) -> pd.DataFrame:
    p = proy[(proy["cod_territorio"] == "00") & proy["sexo"].isin(["H", "M"]) &
             (proy["cod_indicador"] == "POBLACION") & (proy["edicion_proyeccion"] == edicion)]
    a_grupo = {q: g for g, qs in grupos.items() for q in qs}
    p = p[p["grupo_edad"].isin(a_grupo)].assign(grupo_eaps=lambda d: d["grupo_edad"].map(a_grupo))
    out = p.groupby(["anio", "escenario", "sexo", "grupo_eaps"], as_index=False)["valor"].sum()
    return out.rename(columns={"escenario": "escenario_kostat", "grupo_eaps": "grupo_edad", "valor": "poblacion"})


def factor_cobertura(hist: pd.DataFrame, grupos: dict[str, list[str]], anio_base: int) -> pd.DataFrame:
    h = hist[(hist["cod_territorio"] == "00") & hist["sexo"].isin(["H", "M"]) & (hist["anio"] == anio_base)]
    eaps = h[(h["cod_indicador"] == "POB_15MAS") & h["grupo_edad"].isin(grupos)].set_index(["sexo", "grupo_edad"])["valor"]
    a_grupo = {q: g for g, qs in grupos.items() for q in qs}
    pob = h[(h["cod_indicador"] == "POBLACION") & h["grupo_edad"].isin(a_grupo)]
    pob = pob.assign(grupo=pob["grupo_edad"].map(a_grupo)).groupby(["sexo", "grupo"])["valor"].sum()
    pob.index.names = ["sexo", "grupo_edad"]
    return (eaps / pob).rename("factor_cobertura").reset_index()


def _supuesto_a(base: pd.DataFrame, anios: list[int]) -> tuple[pd.DataFrame, dict]:
    return base.merge(pd.DataFrame({"anio": anios}), how="cross"), {}


def _supuesto_b(tasas: pd.DataFrame, base: pd.DataFrame, anios: list[int], p: dict, anio_base: int):
    ini, fin = p["anios_tendencia"]
    pendientes = {}
    for (sexo, grupo), g in tasas[tasas["anio"].between(ini, fin)].groupby(["sexo", "grupo_edad"]):
        # Con menos de 3 años no hay tendencia confiable: la tasa queda constante.
        pendientes[(sexo, grupo)] = float(np.polyfit(g["anio"], g["tasa"], 1)[0]) if len(g) >= 3 else 0.0
    filas = []
    for r in base.itertuples():
        m = pendientes.get((r.sexo, r.grupo_edad), 0.0)
        for a in anios:
            t = r.tasa + m * (min(a, p["congelar_desde"]) - anio_base)
            t = np.clip(t, r.tasa - p["cambio_maximo_pp"], r.tasa + p["cambio_maximo_pp"])
            filas.append((a, r.sexo, r.grupo_edad, float(np.clip(t, p["piso"], p["tope"]))))
    calculado = {f"pendiente_pp_por_anio[{s},{g}]": round(m, 4) for (s, g), m in pendientes.items()}
    return pd.DataFrame(filas, columns=["anio", "sexo", "grupo_edad", "tasa"]), calculado


def _supuesto_c(base: pd.DataFrame, oecd: pd.DataFrame, anios: list[int], p: dict, anio_base: int):
    ultimo = oecd[oecd["anio"] <= anio_base]["anio"].max()
    ref = oecd[oecd["anio"] == ultimo].set_index(["sexo", "grupo_edad"])["valor"]
    edades_oecd = {"Y15T24": "15-24", "Y25T54": "25-54", "Y55T64": "55-64"}
    objetivos, sin_dato = {}, []
    for (sexo, grupo) in base.set_index(["sexo", "grupo_edad"]).index:
        pesos = p["equivalencias_oecd"].get(grupo)
        if not pesos:   # sin equivalencia (15-19, 60+): se mantiene constante
            continue
        claves = [(sexo, edades_oecd[e]) for e in pesos]
        if all(k in ref.index for k in claves):
            objetivos[(sexo, grupo)] = sum(w * ref[k] for w, k in zip(pesos.values(), claves))
        else:
            sin_dato.append(f"{sexo},{grupo}")
    filas = []
    horizonte = p["anio_convergencia"] - anio_base
    for r in base.itertuples():
        obj = objetivos.get((r.sexo, r.grupo_edad), r.tasa)
        for a in anios:
            filas.append((a, r.sexo, r.grupo_edad, r.tasa + (obj - r.tasa) * min(1.0, (a - anio_base) / horizonte)))
    calculado = {"anio_referencia_oecd": int(ultimo), "constantes_por_falta_de_dato_oecd": sin_dato,
                 **{f"objetivo_pct[{s},{g}]": round(v, 2) for (s, g), v in objetivos.items()}}
    return pd.DataFrame(filas, columns=["anio", "sexo", "grupo_edad", "tasa"]), calculado


def _supuesto_d(base: pd.DataFrame, anios: list[int], p: dict, anio_base: int):
    """La tasa femenina cierra linealmente una fracción de la brecha con la masculina hasta el año meta; la masculina
    queda constante. Si la tasa femenina ya es mayor (brecha negativa), no cambia."""
    t = base.set_index(["sexo", "grupo_edad"])["tasa"]
    brecha = (t.xs("H") - t.xs("M")).rename("brecha")
    cierre = brecha.clip(lower=0)
    filas = []
    for r in base.itertuples():
        for a in anios:
            avance = min(max((a - anio_base) / (p["anio_meta"] - anio_base), 0.0), 1.0) * p["fraccion_cierre"]
            tasa = r.tasa + avance * cierre[r.grupo_edad] if r.sexo == "M" else r.tasa
            filas.append((a, r.sexo, r.grupo_edad, tasa))
    calculado = {f"brecha_base_pp[{g}]": round(float(v), 2) for g, v in brecha.items()}
    return pd.DataFrame(filas, columns=["anio", "sexo", "grupo_edad", "tasa"]), calculado


def calcular(hist: pd.DataFrame, proy: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = cfg["gold"]
    p = g["escenarios_fuerza_laboral"]
    anio_base = p["anio_base"]
    pob = poblacion_grupos(proy, p["grupos"], cfg["silver"]["ediciones"]["kosis_nacional"])
    pob = pob[pob["escenario_kostat"].isin(p.get("escenarios_kostat", ["medio", "alto", "bajo"]))]
    anios = sorted(pob["anio"].unique())
    tasas = tasas_eaps(hist, list(p["grupos"]))
    base = tasas[tasas["anio"] == anio_base].drop(columns="anio")
    if len(base) != 2 * len(p["grupos"]):
        raise ValueError(f"Faltan tasas EAPS del año base {anio_base}: hay {len(base)} de {2 * len(p['grupos'])}")
    if p.get("calibrar_cobertura_eaps"):
        factores = factor_cobertura(hist, p["grupos"], anio_base)
        if len(factores.dropna()) != len(base):
            raise ValueError("No se pudo calcular el factor de cobertura EAPS para todos los grupos del año base")
    else:
        factores = base[["sexo", "grupo_edad"]].assign(factor_cobertura=1.0)
    oecd = hist[(hist["cod_territorio"] == "OED") & (hist["cod_indicador"] == "TASA_PARTICIPACION") & hist["sexo"].isin(["H", "M"])]

    escenarios, supuestos = [], []
    for sid, sp in p["supuestos"].items():
        if sid == "A":
            t, calc = _supuesto_a(base, anios)
        elif sid == "B":
            t, calc = _supuesto_b(tasas, base, anios, sp, anio_base)
        elif sid == "C":
            t, calc = _supuesto_c(base, oecd, anios, sp, anio_base)
        elif sid == "D":
            t, calc = _supuesto_d(base, anios, sp, anio_base)
        else:
            raise ValueError(f"Supuesto desconocido en config.yaml: {sid}")
        e = pob.merge(t, on=["anio", "sexo", "grupo_edad"]).merge(factores, on=["sexo", "grupo_edad"])
        e["fuerza_laboral"] = e["poblacion"] * e["factor_cobertura"] * e["tasa"] / 100
        escenarios.append(e.assign(id_supuesto=sid))
        params = {k: v for k, v in sp.items() if k not in ("nombre", "descripcion")}
        supuestos.append({"id_supuesto": sid, "nombre": sp["nombre"], "descripcion": " ".join(sp["descripcion"].split()),
                          "parametros": {"anio_base": anio_base, **params, **calc}})
    out = pd.concat(escenarios, ignore_index=True).rename(columns={"tasa": "tasa_participacion"})
    out["version_modelo"] = g["version_modelo"]
    sup = pd.DataFrame(supuestos).assign(version_modelo=g["version_modelo"])
    return out, sup


def sensibilidad(hist: pd.DataFrame, proy: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Fuerza laboral total (escenario KOSTAT medio) con variantes de los parámetros de B y C (config.yaml)."""
    import copy
    filas = []
    for sid, variantes in cfg["gold"]["escenarios_fuerza_laboral"].get("sensibilidad", {}).items():
        for variante in variantes:
            c = copy.deepcopy(cfg)
            sp = c["gold"]["escenarios_fuerza_laboral"]["supuestos"]
            c["gold"]["escenarios_fuerza_laboral"]["supuestos"] = {sid: {**sp[sid], **variante}}
            esc, _ = calcular(hist, proy, c)
            tot = esc[esc["escenario_kostat"] == "medio"].groupby("anio")["fuerza_laboral"].sum().reset_index()
            etiqueta = ", ".join(f"{k}={v}" for k, v in variante.items())
            filas.append(tot.assign(id_supuesto=sid, variante=etiqueta))
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
