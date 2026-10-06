"""Lee los archivos de bronze a formato largo con las etiquetas originales de cada fuente (sin homologar).

De cada archivo se usa la versión más reciente (la de la carpeta de fecha más nueva que lo contenga).
Los nombres de archivo y encodings de KOSIS salen del catálogo de config.yaml (kosis.archivos).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
BRONZE = RAIZ / "data" / "bronze"


@lru_cache(maxsize=1)
def _config() -> dict:
    with open(RAIZ / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def archivo_reciente(fuente: str, patron: str) -> Path:
    candidatos = sorted((BRONZE / fuente).glob(f"*/{patron}"), key=lambda p: (p.parent.name, p.name))
    if not candidatos:
        raise FileNotFoundError(f"No hay '{patron}' en {BRONZE / fuente}/<fecha>/ (correr: python main.py --fuente {fuente})")
    return candidatos[-1]


def archivos_recientes(fuente: str, patron: str) -> dict[str, Path]:
    """Versión más reciente de cada archivo distinto que cumple el patrón (sin los *_metadata.json)."""
    out = {}
    for p in sorted((BRONZE / fuente).glob(f"*/{patron}"), key=lambda p: (p.parent.name, p.name)):
        if not p.stem.endswith("_metadata"):
            out[p.stem] = p
    return out


def crudo_json(archivo: Path):
    """Contenido de un crudo JSON. Acepta el formato del pipeline (respuesta de la API tal cual) y el de las
    descargas exploratorias previas (respuesta envuelta en {"registro": ...} junto con su metadata)."""
    data = json.loads(archivo.read_text(encoding="utf-8"))
    return data["registro"] if isinstance(data, dict) and "registro" in data else data


def _a_numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.astype(str).str.strip().replace({"-": None, "": None, "nan": None}), errors="coerce")


# ---------------------------------------------------------------- KOSIS

def archivo_kosis(nombre: str) -> tuple[Path, str]:
    spec = _config()["kosis"]["archivos"][nombre]
    return archivo_reciente("kosis", spec["patron"]), spec["encoding"]


def _kosis_encabezado_doble(nombre: str, dims: list[str]) -> pd.DataFrame:
    # Fila 0 = periodo, fila 1 = ítem; las primeras columnas son las dimensiones.
    # Solo se conservan columnas anuales (periodo de 4 dígitos); los meses sueltos se descartan.
    archivo, encoding = archivo_kosis(nombre)
    raw = pd.read_csv(archivo, encoding=encoding, header=None, dtype=str)
    n = len(dims)
    periodo = raw.iloc[0, n:]
    anuales = [j for j, p in zip(range(n, raw.shape[1]), periodo) if re.fullmatch(r"\d{4}", str(p).strip())]
    cuerpo = raw.iloc[2:].reset_index(drop=True)
    partes = []
    for j in anuales:
        parte = cuerpo.iloc[:, :n].copy()
        parte.columns = dims
        parte["anio"] = int(raw.iloc[0, j])
        parte["item"] = raw.iloc[1, j].strip()
        parte["valor"] = _a_numero(cuerpo.iloc[:, j])
        partes.append(parte)
    return pd.concat(partes, ignore_index=True)


def _kosis_ancho(nombre: str, dims: list[str], patron_anio: str) -> pd.DataFrame:
    archivo, encoding = archivo_kosis(nombre)
    df = pd.read_csv(archivo, encoding=encoding, dtype=str)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    cols_anio = [c for c in df.columns if re.fullmatch(patron_anio, c.strip())]
    largo = df.melt(id_vars=dims, value_vars=cols_anio, var_name="anio", value_name="valor")
    largo["anio"] = largo["anio"].str.extract(r"(\d{4})", expand=False).astype(int)
    largo["valor"] = _a_numero(largo["valor"])
    return largo


def kosis_vitales_nacional() -> pd.DataFrame:
    df = _kosis_ancho("vitales_nacional", ["By items"], r"\d{4}")
    return df.rename(columns={"By items": "item"}).assign(territorio="Whole country")


def kosis_vitales_sido() -> pd.DataFrame:
    return _kosis_encabezado_doble("vitales_sido", ["territorio"])


def kosis_tfr_sido() -> pd.DataFrame:
    return _kosis_encabezado_doble("tfr_sido", ["territorio"])


def kosis_eaps_sido() -> pd.DataFrame:
    return _kosis_encabezado_doble("eaps_sido", ["territorio"])


def kosis_eaps_sexo_edad() -> pd.DataFrame:
    return _kosis_encabezado_doble("eaps_sexo_edad", ["sexo", "edad"])


def kosis_poblacion_nacional() -> pd.DataFrame:
    # 2000-2021 población estimada, 2022-2072 proyección escenario medio.
    df = _kosis_ancho("poblacion_nacional", ["가정별", "성별", "연령별"], r"\d{4}")
    return df.rename(columns={"가정별": "escenario", "성별": "sexo", "연령별": "edad"}).assign(territorio="Whole country")


def kosis_proyeccion_escenarios() -> pd.DataFrame:
    df = _kosis_ancho("proyeccion_escenarios", ["시나리오별", "성별", "연령별"], r"\d{4} 년")
    return df.rename(columns={"시나리오별": "escenario", "성별": "sexo", "연령별": "edad"}).assign(territorio="Whole country")


def kosis_poblacion_sido() -> pd.DataFrame:
    # 2000-2021 población estimada, 2022-2052 proyección escenario medio.
    df = _kosis_ancho("poblacion_sido", ["By scenarios", "By province", "By gender", "By age"], r"\d{4} Year")
    return df.rename(columns={"By scenarios": "escenario", "By province": "territorio",
                              "By gender": "sexo", "By age": "edad"})


# ---------------------------------------------------------------- OECD

def oecd(dataset: str) -> pd.DataFrame:
    # dataset: productividad | fuerza_laboral | fecundidad_nacimientos | dependencia_vejez
    df = pd.read_csv(archivo_reciente("oecd", f"{dataset}.csv"))
    return df.rename(columns={"TIME_PERIOD": "anio", "OBS_VALUE": "valor"})


# ---------------------------------------------------------------- World Bank

def worldbank() -> pd.DataFrame:
    filas = []
    for archivo in archivos_recientes("worldbank", "*.json").values():
        for r in crudo_json(archivo)[1] or []:
            filas.append({"indicador": r["indicator"]["id"], "iso3": r["countryiso3code"],
                          "pais": r["country"]["value"], "anio": int(r["date"]), "valor": r["value"]})
    df = pd.DataFrame(filas)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df


# ---------------------------------------------------------------- UN WPP

VARIANTES_UNWPP = {4: "Median", 9: "High-fertility", 10: "Low-fertility"}


def unwpp(solo_variantes_proyecto: bool = True) -> pd.DataFrame:
    df = pd.DataFrame(crudo_json(archivo_reciente("unwpp", "poblacion_edad_sexo.json")))
    if solo_variantes_proyecto:
        df = df[df["variantId"].isin(VARIANTES_UNWPP)]
    df = df.rename(columns={"timeLabel": "anio", "sex": "sexo", "ageLabel": "edad", "variant": "variante", "value": "valor"})
    df["anio"] = df["anio"].astype(int)
    # estimateMethod separa histórico (Interpolation, 2000-2021) de proyección (Projection, 2022+); estimateType no.
    return df[["variante", "estimateType", "estimateMethod", "anio", "sexo", "edad", "ageStart", "valor"]].reset_index(drop=True)
