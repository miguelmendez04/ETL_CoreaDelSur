"""Homologación de etiquetas de las fuentes a los códigos de las dimensiones (config/mappings/).

- Territorio, sexo y escenario: diccionario explícito en etiquetas.csv (inglés y coreano) + códigos/ISO3 de
  territorios.csv. Nunca traducción automática.
- Edad: regla única ("0 - 4세", "0-4 Years old" -> "0-4"; "100세 이상", "100 Years old & over" -> "100+";
  "계"/"Total" -> "TOTAL"), luego exclusiones y agrupaciones de config.yaml y validación contra dim_edad.
Lo que no se puede homologar va a rechazos con su motivo; nada se descarta en silencio.
"""
import re

import pandas as pd

from src.utils.config import ruta


def cargar_dimensiones() -> dict[str, pd.DataFrame]:
    m = ruta("mappings")
    leer = lambda n, **kw: pd.read_csv(m / f"{n}.csv", encoding="utf-8", dtype=str, keep_default_na=False, **kw)
    return {"territorio": leer("territorios"), "edad": leer("edades"), "sexo": leer("sexo"),
            "indicador": leer("indicadores"), "etiquetas": leer("etiquetas")}


def normalizar_edad(etiqueta) -> str | None:
    if etiqueta is None or pd.isna(etiqueta):
        return None
    e = str(etiqueta).strip()
    if e in ("계", "Total", "TOTAL"):
        return "TOTAL"
    if m := re.match(r"^(\d+)\s*-\s*(\d+)", e):
        return f"{int(m.group(1))}-{int(m.group(2))}"
    if m := re.match(r"^(\d+)\s*(?:\+|세\s*이상|years? old (?:&|and) over)", e, flags=re.IGNORECASE):
        return f"{int(m.group(1))}+"
    return None


def _diccionario(dims: dict, dimension: str) -> dict[str, str]:
    et = dims["etiquetas"]
    d = dict(zip(et.loc[et["dimension"] == dimension, "etiqueta"], et.loc[et["dimension"] == dimension, "codigo"]))
    if dimension == "territorio":   # también se aceptan el código propio, el nombre en inglés y el ISO3
        t = dims["territorio"]
        for col in ("cod_territorio", "nombre_en", "iso3"):
            d.update({k: c for k, c in zip(t[col], t["cod_territorio"]) if k})
    if dimension == "sexo":
        d.update({c: c for c in dims["sexo"]["cod_sexo"]})
    return d


def homologar(cand: pd.DataFrame, dims: dict, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Devuelve (homologados, rechazos, conteo de filas fuera de alcance por motivo)."""
    s = cfg["silver"]
    df = cand.copy()
    df["cod_territorio"] = df["territorio_src"].map(_diccionario(dims, "territorio"))
    df["sexo"] = df["sexo_src"].map(_diccionario(dims, "sexo"))
    edad = df["edad_src"].map(normalizar_edad)
    df["grupo_edad"] = edad.replace(s["edades_agrupadas"])
    df["escenario"] = df["escenario_src"].map(_diccionario(dims, "escenario"))
    fuera = {}

    # Fuera de alcance (documentado en config.yaml): agregados de edad solapados y escenarios KOSTAT no usados.
    excl_edad = edad.isin(s["edades_excluidas"]) & (df["fuente"] == "KOSIS")   # solapados en las tablas KOSIS
    fuera["edad_agregada_solapada"] = int(excl_edad.sum())
    proy = df["nivel"] == "proyeccion"
    otro_escenario = proy & df["escenario_src"].notna() & df["escenario"].isna()
    fuera["escenario_no_usado"] = int(otro_escenario.sum())
    df = df[~excl_edad & ~otro_escenario]

    rech = []
    reglas = [
        (df["cod_territorio"] == "EXCLUIR", "territorio_excluido", lambda r: f"territorio '{r.territorio_src}' excluido (ver etiquetas.csv)"),
        (df["cod_territorio"].isna(), "etiqueta_no_mapeada", lambda r: f"territorio '{r.territorio_src}' sin código"),
        (df["sexo"].isna(), "etiqueta_no_mapeada", lambda r: f"sexo '{r.sexo_src}' sin código"),
        (~df["grupo_edad"].isin(dims["edad"]["cod_grupo_edad"]), "etiqueta_no_mapeada", lambda r: f"edad '{r.edad_src}' sin grupo"),
    ]
    malo = pd.Series(False, index=df.index)
    for mascara, regla, motivo in reglas:
        nuevos = mascara & ~malo
        if nuevos.any():
            rech.append(rechazos(df[nuevos], regla, motivo))
        malo |= mascara
    return df[~malo], (pd.concat(rech, ignore_index=True) if rech else rechazos(df.iloc[0:0], "", "")), fuera


def rechazos(df: pd.DataFrame, regla: str, motivo) -> pd.DataFrame:
    """Formato de ctl.rechazos: origen, regla, motivo y el registro candidato completo."""
    if df.empty:
        return pd.DataFrame(columns=["destino", "tabla_origen", "id_registro_origen", "regla", "motivo", "registro"])
    motivos = [motivo(r) if callable(motivo) else motivo for r in df.itertuples()]
    registros = df.drop(columns=[c for c in ("fecha_extraccion",) if c in df]).astype(object).where(df.notna(), None)
    return pd.DataFrame({
        "destino": df["nivel"].map({"historico": "silver.fact_historico", "proyeccion": "silver.fact_proyeccion"}).values,
        "tabla_origen": df["tabla_origen"].values if "tabla_origen" in df else "pipeline",
        "id_registro_origen": df["id_bronze"].values if "id_bronze" in df else None,
        "regla": regla, "motivo": motivos,
        "registro": registros.to_dict("records"),
    })
