"""World Bank WDI (API v2, sin credenciales). Un dataset = un indicador para todos los países de config.yaml."""
import json
import logging
from datetime import datetime

from src.extract.comun import Extraccion, guardar_crudo, http_get, rango_anios, sha256

FUENTE = "WB"
CARPETA = "worldbank"
log = logging.getLogger("extract.worldbank")


def datasets(cfg: dict) -> list[str]:
    return list(cfg["worldbank"]["datasets"])


def extraer(nombre: str, cfg: dict) -> Extraccion:
    wb, periodo = cfg["worldbank"], cfg["periodo_historico"]
    url = f"{wb['base_url']}/country/{';'.join(wb['paises'])}/indicator/{nombre}"
    params = {"format": "json", "date": f"{periodo['inicio']}:{periodo['fin']}", "per_page": wb["per_page"]}

    meta, datos, pagina = None, [], 1
    while True:
        cuerpo = http_get(url, {**params, "page": pagina}).json()
        if len(cuerpo) < 2:  # la API responde [{"message": [...]}] cuando el código o los parámetros son inválidos
            raise ValueError(f"World Bank rechazó la consulta: {cuerpo[0]}")
        meta = meta or cuerpo[0]
        datos += cuerpo[1] or []
        if pagina >= cuerpo[0]["pages"]:
            break
        pagina += 1
    fecha = datetime.now().astimezone()  # con zona horaria: Postgres guarda timestamptz

    # Crudo = respuesta de la API ([metadatos de paginación, observaciones]), con todas las páginas unidas.
    archivo = guardar_crudo(CARPETA, f"{nombre}.json", json.dumps([meta, datos], ensure_ascii=False).encode("utf-8"))
    avisos = []
    nulos = sum(d["value"] is None for d in datos)
    if not datos:
        avisos.append("la API devolvió 0 registros")
    elif nulos:
        anios_nulos = sorted({d["date"] for d in datos if d["value"] is None})
        avisos.append(f"{nulos} valores nulos (años {', '.join(anios_nulos[-3:])}{'...' if len(anios_nulos) > 3 else ''})")
    return Extraccion(
        fuente=FUENTE, dataset=nombre, metodo="api", url=url, params=params, registros=datos,
        archivo=archivo, hash_archivo=sha256(archivo.read_bytes()), fecha_extraccion=fecha,
        resumen={"paises": len({d["countryiso3code"] for d in datos}), "anios": rango_anios(d["date"] for d in datos),
                 "nulos": nulos, "lastupdated": meta.get("lastupdated")},
        avisos=avisos,
    )
