"""UN World Population Prospects (Data Portal API, requiere token gratuito en .env)."""
import json
import logging
import os
from datetime import datetime

from src.extract.comun import Extraccion, guardar_crudo, http_get, rango_anios, sha256

FUENTE = "UNWPP"
CARPETA = "unwpp"
log = logging.getLogger("extract.unwpp")


def datasets(cfg: dict) -> list[str]:
    return list(cfg["unwpp"]["datasets"])


def extraer(nombre: str, cfg: dict) -> Extraccion:
    un = cfg["unwpp"]
    ds = un["datasets"][nombre]
    token = os.getenv(un["token_env"])
    if not token:
        raise RuntimeError(f"Falta {un['token_env']} en .env. Token gratuito: "
                           "https://population.un.org/dataportalapi/token/index.html")
    url = (f"{un['base_url']}/data/indicators/{ds['indicator_id']}/locations/{ds['location_code']}"
           f"/start/{ds['periodo']['inicio']}/end/{ds['periodo']['fin']}")
    params = {"format": "json", "pageSize": un["page_size"]}
    headers = {"Authorization": f"Bearer {token}"}  # el token nunca se guarda en params ni en metadata

    filas, pagina, paginas = [], 1, None
    while paginas is None or pagina <= paginas:
        cuerpo = http_get(url, {**params, "pageNumber": pagina}, headers=headers).json()
        filas += cuerpo["data"]
        paginas = cuerpo.get("pages", 1)
        if pagina == 1 or pagina % 10 == 0 or pagina == paginas:
            log.info("  página %d/%d (%d registros acumulados)", pagina, paginas, len(filas))
        pagina += 1
    fecha = datetime.now().astimezone()  # con zona horaria: Postgres guarda timestamptz

    contenido = json.dumps(filas, ensure_ascii=False).encode("utf-8")
    archivo = guardar_crudo(CARPETA, f"{nombre}.json", contenido)
    esperadas = set(ds.get("variantes_a_usar", {}).values())
    presentes = {f["variantId"] for f in filas}
    avisos = [f"faltan variantes {sorted(esperadas - presentes)}"] if esperadas - presentes else []
    return Extraccion(
        fuente=FUENTE, dataset=nombre, metodo="api", url=url,
        params={**params, "indicator_id": ds["indicator_id"], "location_code": ds["location_code"]},
        registros=filas, archivo=archivo, hash_archivo=sha256(contenido), fecha_extraccion=fecha,
        resumen={"variantes": len(presentes), "anios": rango_anios(f["timeLabel"] for f in filas), "paginas": paginas},
        avisos=avisos,
    )
