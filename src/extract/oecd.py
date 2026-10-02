"""OECD SDMX REST (sin credenciales, requiere User-Agent). Un dataset = un dataflow + clave de config.yaml."""
import io
import logging
from datetime import datetime

import pandas as pd

from src.extract.comun import Extraccion, guardar_crudo, http_get, rango_anios, sha256

FUENTE = "OECD"
CARPETA = "oecd"
log = logging.getLogger("extract.oecd")


def datasets(cfg: dict) -> list[str]:
    return list(cfg["oecd"]["datasets"])


def extraer(nombre: str, cfg: dict) -> Extraccion:
    oe = cfg["oecd"]
    ds = oe["datasets"][nombre]
    variables = {"paises": "+".join(oe["paises_comparacion"]), "regiones_kor_tl3": "+".join(oe.get("regiones_kor_tl3", []))}
    clave = ds["clave"].format(**variables)
    url = f"{oe['base_url']}/data/{ds['dataflow']}/{clave}"
    params = {"startPeriod": ds.get("periodo", cfg["periodo_historico"])["inicio"], "format": oe["formato"]}

    r = http_get(url, params, headers={"User-Agent": cfg["extraccion"]["user_agent"]})
    fecha = datetime.now().astimezone()  # con zona horaria: Postgres guarda timestamptz
    archivo = guardar_crudo(CARPETA, f"{nombre}.csv", r.content)

    # Todo como texto y sin convertir vacíos a NaN: bronze guarda el CSV tal como llegó.
    df = pd.read_csv(io.BytesIO(r.content), dtype=str, keep_default_na=False)
    avisos = []
    kor = df[df["REF_AREA"] == "KOR"] if "REF_AREA" in df else df.iloc[0:0]
    if kor.empty:
        avisos.append("la respuesta no trae datos de KOR")
    medidas_esperadas = set(ds.get("medidas", {}))
    if medidas_esperadas and "MEASURE" in df:
        faltan = medidas_esperadas - set(df["MEASURE"])
        if faltan:
            avisos.append(f"medidas sin datos: {', '.join(sorted(faltan))}")
    return Extraccion(
        fuente=FUENTE, dataset=nombre, metodo="api", url=url,
        params={**params, "dataflow": ds["dataflow"], "clave": clave},
        registros=df.to_dict("records"), archivo=archivo, hash_archivo=sha256(r.content), fecha_extraccion=fecha,
        resumen={"areas": df["REF_AREA"].nunique() if "REF_AREA" in df else None,
                 "medidas": sorted(df["MEASURE"].unique()) if "MEASURE" in df else None,
                 "anios": rango_anios(df["TIME_PERIOD"].str[:4]) if "TIME_PERIOD" in df else None,
                 "anios_kor": rango_anios(kor["TIME_PERIOD"].str[:4]) if not kor.empty else None},
        avisos=avisos,
    )
