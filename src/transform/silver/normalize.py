"""Bronze -> formato largo: una fila por valor, todavía con las etiquetas originales de la fuente.

Cada función recibe un DatasetBronze (src/transform/desde_bronze.py) y devuelve "candidatos" con columnas
COLUMNAS. La homologación de etiquetas a códigos se hace después (homologacion.py) y la validación en
src/quality/validate.py; aquí solo se reestructura y se elige qué ítems pasan a silver según config.yaml.
"""
import re

import pandas as pd

from src.transform.silver.desde_bronze import DatasetBronze

COLUMNAS = ["nivel", "anio", "territorio_src", "sexo_src", "edad_src", "escenario_src", "cod_indicador",
            "valor_txt", "factor", "fuente", "dataset", "tabla_origen", "id_bronze", "id_carga_origen",
            "fecha_extraccion", "edicion_proyeccion", "version_publicacion"]

ANIO_ANCHO = re.compile(r"^(\d{4})(?: Year| 년)?$")      # "2000", "2000 Year", "2022 년"
ANIO_DOBLE = re.compile(r"^(\d{4}) \| (.+)$")             # "2000 | Live births(persons)" (los meses "2025.08 | ..." no calzan)


def _base(ds: DatasetBronze, tabla: str, version: str) -> dict:
    return {"fuente": ds.fuente, "dataset": ds.dataset, "tabla_origen": tabla, "id_carga_origen": ds.id_carga,
            "fecha_extraccion": ds.fecha_extraccion, "version_publicacion": version}


def _completar(df: pd.DataFrame, **valores) -> pd.DataFrame:
    for col, val in valores.items():
        df[col] = val
    for col in COLUMNAS:
        if col not in df:
            df[col] = None
    return df[COLUMNAS]


# ------------------------------------------------------------------ KOSIS

def _version_kosis(ds: DatasetBronze) -> str:
    p = ds.parametros
    return f"KOSIS {p.get('tbl_id') or p.get('tabla_kosis', '')} (descarga {ds.fecha_extraccion:%Y-%m-%d})".strip()


def _kosis_ancho(ds: DatasetBronze, dims: dict[str, str]) -> pd.DataFrame:
    """Archivos con años como columnas. dims: {columna original: nombre interno}."""
    reg = ds.registros
    anios = {c: int(m.group(1)) for c in reg.columns if (m := ANIO_ANCHO.match(c))}
    largo = reg.melt(id_vars=["id_bronze", *dims], value_vars=list(anios), var_name="col", value_name="valor_txt")
    largo["anio"] = largo.pop("col").map(anios)
    return largo.rename(columns=dims)


def _kosis_doble(ds: DatasetBronze, dims: dict[str, str], items: dict) -> pd.DataFrame:
    """Archivos con encabezado doble ('periodo | ítem'). Solo columnas anuales de los ítems configurados."""
    reg = ds.registros
    cols = {}
    for c in reg.columns:
        m = ANIO_DOBLE.match(c)
        if m and m.group(2) in items:
            cols[c] = (int(m.group(1)), m.group(2))
    largo = reg.melt(id_vars=["id_bronze", *dims], value_vars=list(cols), var_name="col", value_name="valor_txt")
    largo["anio"] = largo["col"].map(lambda c: cols[c][0])
    item = largo.pop("col").map(lambda c: cols[c][1])
    largo["cod_indicador"] = item.map(lambda i: items[i]["indicador"])
    largo["factor"] = item.map(lambda i: items[i].get("factor", 1))
    return largo.rename(columns=dims)


def kosis_vitales_sido(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_doble(ds, {"By administrative divisions": "territorio_src"}, cfg["silver"]["items_kosis"]["vitales_sido"])
    return _completar(df, nivel="historico", sexo_src="Total", edad_src="Total", **_base(ds, "bronze.kosis", _version_kosis(ds)))


def kosis_tfr_sido(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_doble(ds, {"By si(city), gun(county) and gu(borough)": "territorio_src"}, cfg["silver"]["items_kosis"]["tfr_sido"])
    return _completar(df, nivel="historico", sexo_src="Total", edad_src="Total", **_base(ds, "bronze.kosis", _version_kosis(ds)))


def kosis_eaps_sido(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_doble(ds, {"By province": "territorio_src"}, cfg["silver"]["items_kosis"]["eaps"])
    # El total nacional sale de eaps_sexo_edad (mismos valores, validado), que además trae sexo y edad.
    df = df[df["territorio_src"] != "Total"]
    return _completar(df, nivel="historico", sexo_src="Total", edad_src="15+", **_base(ds, "bronze.kosis", _version_kosis(ds)))


def kosis_eaps_sexo_edad(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_doble(ds, {"By gender": "sexo_src", "By age group": "edad_src"}, cfg["silver"]["items_kosis"]["eaps"])
    df["edad_src"] = df["edad_src"].replace({"Total": "15+"})   # en la EAPS el total es la población de 15 años y más
    return _completar(df, nivel="historico", territorio_src="Whole country", **_base(ds, "bronze.kosis", _version_kosis(ds)))


def _poblacion(df: pd.DataFrame, cfg: dict, edicion: str) -> pd.DataFrame:
    """Separa histórico (<= periodo_historico_hasta) y proyección (>= proyeccion_desde) de un mismo archivo."""
    s = cfg["silver"]
    df["cod_indicador"], df["factor"] = "POBLACION", 1
    df["nivel"] = df["anio"].map(lambda a: "historico" if a <= s["periodo_historico_hasta"] else "proyeccion")
    df = df[(df["nivel"] == "historico") | (df["anio"] >= s["proyeccion_desde"])].copy()
    df["edicion_proyeccion"] = df["nivel"].map({"proyeccion": edicion, "historico": None})
    df.loc[df["nivel"] == "historico", "escenario_src"] = None
    return df


def kosis_poblacion_nacional(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_ancho(ds, {"가정별": "escenario_src", "성별": "sexo_src", "연령별": "edad_src"})
    df = _poblacion(df, cfg, cfg["silver"]["ediciones"]["kosis_nacional"])
    return _completar(df, territorio_src="Whole country", **_base(ds, "bronze.kosis", _version_kosis(ds)))


def kosis_poblacion_sido(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    df = _kosis_ancho(ds, {"By scenarios": "escenario_src", "By province": "territorio_src",
                           "By gender": "sexo_src", "By age": "edad_src"})
    df = df[df["territorio_src"] != "Whole country"]   # el nacional sale de la tabla nacional (idéntica, validado)
    df = _poblacion(df, cfg, cfg["silver"]["ediciones"]["kosis_sido"])
    return _completar(df, **_base(ds, "bronze.kosis", _version_kosis(ds)))


def kosis_proyeccion_escenarios(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    """Escenarios alto y bajo (el medio sale de la tabla nacional). Solo años de proyección."""
    df = _kosis_ancho(ds, {"시나리오별": "escenario_src", "성별": "sexo_src", "연령별": "edad_src"})
    df = _poblacion(df, cfg, cfg["silver"]["ediciones"]["kosis_nacional"])
    df = df[df["nivel"] == "proyeccion"]
    return _completar(df, territorio_src="Whole country", **_base(ds, "bronze.kosis", _version_kosis(ds)))


# ------------------------------------------------------------------ World Bank y OECD

def worldbank(ds: DatasetBronze, cfg: dict, regla: dict, incluir_kor: bool) -> pd.DataFrame:
    """Indicador WB para los países de comparación. Corea solo se incluye si World Bank es la fuente maestra del
    indicador (p. ej. PIB_OCUPADO); si la maestra es KOSIS, el dato WB de Corea va solo a conciliación."""
    reg = ds.registros
    if not incluir_kor:
        reg = reg[reg["countryiso3code"] != "KOR"]
    df = pd.DataFrame({"id_bronze": reg["id_bronze"], "territorio_src": reg["countryiso3code"],
                       "anio": reg["date"].astype(int), "valor_txt": reg["value"].astype(object)})
    version = f"WDI {ds.parametros.get('resumen', {}).get('lastupdated', '')}".strip()
    return _completar(df, nivel="historico", sexo_src="Total", edad_src=regla.get("grupo_edad", "TOTAL"),
                      cod_indicador=regla["indicador"], factor=1, **_base(ds, "bronze.worldbank_wdi", version))


def oecd_productividad(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    reg = ds.registros
    if "TRANSFORMATION" in reg:
        reg = reg[reg["TRANSFORMATION"] == "N"]   # solo niveles (no tasas de crecimiento)
    df = pd.DataFrame({"id_bronze": reg["id_bronze"], "territorio_src": reg["REF_AREA"],
                       "anio": reg["TIME_PERIOD"].str[:4].astype(int), "valor_txt": reg["OBS_VALUE"]})
    return _completar(df, nivel="historico", sexo_src="Total", edad_src="TOTAL", cod_indicador="PIB_HORA", factor=1,
                      **_base(ds, "bronze.oecd_sdmx", ds.parametros.get("dataflow", "OECD")))


def oecd_participacion(ds: DatasetBronze, cfg: dict) -> pd.DataFrame:
    """Promedio OCDE de la tasa de participación por sexo y edad (comparación internacional e insumo del
    escenario C). Corea no se toma de aquí: su maestra es la EAPS."""
    reg = ds.registros
    edades = {"Y15T24": "15-24", "Y25T54": "25-54", "Y55T64": "55-64"}
    reg = reg[(reg["REF_AREA"] == "OECD") & reg["SEX"].isin(["M", "F"]) & reg["AGE"].isin(edades)]
    df = pd.DataFrame({"id_bronze": reg["id_bronze"], "territorio_src": "OED", "sexo_src": reg["SEX"].map({"M": "Male", "F": "Female"}),
                       "edad_src": reg["AGE"].map(edades), "anio": reg["TIME_PERIOD"].str[:4].astype(int),
                       "valor_txt": reg["OBS_VALUE"]})
    return _completar(df, nivel="historico", cod_indicador="TASA_PARTICIPACION", factor=1,
                      **_base(ds, "bronze.oecd_sdmx", ds.parametros.get("dataflow", "OECD")))
