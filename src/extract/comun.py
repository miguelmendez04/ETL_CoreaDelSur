"""Piezas comunes de los extractores: resultado de una extracción, HTTP con reintentos y archivos crudos en bronze."""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from src.utils.config import RAIZ, cargar_config, ruta

log = logging.getLogger("extract")
CORRIDA = datetime.now()   # una ejecución del pipeline = una carpeta de fecha por fuente


@dataclass
class Extraccion:
    """Lo que devuelve cada extractor: el crudo guardado en disco y sus registros listos para bronze.*"""
    fuente: str                      # valor de la columna `fuente`: KOSIS | WB | OECD | UNWPP
    dataset: str                     # clave del dataset en config.yaml
    metodo: str                      # api | descarga_manual
    url: str
    params: dict                     # parámetros de la consulta (nunca credenciales)
    registros: list[dict]            # un dict por registro, tal como vino de la fuente
    archivo: Path                    # archivo crudo en data/bronze/<fuente>/<fecha>/
    hash_archivo: str                # sha256 del contenido crudo
    fecha_extraccion: datetime
    columnas_extra: dict = field(default_factory=dict)   # columnas propias de la tabla bronze (p. ej. org_id, tbl_id)
    resumen: dict = field(default_factory=dict)          # cobertura detectada (años, países, series...)
    avisos: list[str] = field(default_factory=list)      # hallazgos que no impiden la carga


def sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def hash_registro(registro: dict) -> str:
    return sha256(json.dumps(registro, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def http_get(url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response:
    """GET con reintentos ante errores de red, 429 y 5xx. Los 4xx restantes (401, 403, 404) fallan de inmediato."""
    cfg = cargar_config()["extraccion"]
    for intento in range(1, cfg["reintentos"] + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=cfg["timeout_s"])
            if r.status_code < 400:
                return r
            if r.status_code != 429 and r.status_code < 500:
                r.raise_for_status()
            motivo = f"HTTP {r.status_code}"
        except requests.HTTPError:
            raise
        except requests.RequestException as e:  # conexión, timeout, respuesta cortada a mitad de descarga
            motivo = type(e).__name__
        if intento == cfg["reintentos"]:
            raise RuntimeError(f"{motivo} tras {intento} intentos: {url}")
        log.warning("  %s (intento %d/%d), reintentando en %ss", motivo, intento, cfg["reintentos"], cfg["espera_reintento_s"])
        time.sleep(cfg["espera_reintento_s"])


def version_reciente(carpeta_fuente: str, patron: str) -> Path | None:
    """Archivo más reciente que cumple el patrón, buscando en todas las carpetas de fecha de la fuente."""
    candidatos = sorted(ruta("bronze").joinpath(carpeta_fuente).glob(f"*/{patron}"), key=lambda p: (p.parent.name, p.name))
    return candidatos[-1] if candidatos else None


def guardar_crudo(carpeta_fuente: str, nombre: str, contenido: bytes) -> Path:
    """Escribe el crudo en data/bronze/<fuente>/<hoy>/<nombre> sin sobrescribir nunca un archivo distinto.

    Si la versión más reciente de ese archivo tiene exactamente el mismo contenido, se reutiliza (no se duplica).
    Si hoy ya existe una versión con contenido distinto, la nueva se guarda en <hoy>_<HHMMSS>/.
    """
    previo = version_reciente(carpeta_fuente, nombre)
    if previo is not None and sha256(previo.read_bytes()) == sha256(contenido):
        return previo
    hoy = CORRIDA.strftime("%Y-%m-%d")
    destino = ruta("bronze") / carpeta_fuente / hoy / nombre
    if destino.exists():
        destino = ruta("bronze") / carpeta_fuente / f"{hoy}_{CORRIDA:%H%M%S}" / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return destino


def relativa(path: Path) -> str:
    return path.relative_to(RAIZ).as_posix()


def escribir_metadata(ext: Extraccion) -> Path:
    """<archivo>_metadata.json junto al crudo: de dónde salió, cuándo, con qué parámetros, su sha256 y qué contiene.

    Describe solo el archivo, no la carga: el mismo crudo produce siempre el mismo metadata, así que las descargas
    manuales de KOSIS (versionadas en git) no cambian al correr el pipeline en otra base. La carga en que quedó
    cada archivo se busca en ctl.log_cargas por archivo o hash_archivo. Solo se escribe si el contenido cambia.
    """
    destino = ext.archivo.with_name(f"{ext.archivo.stem}_metadata.json")
    texto = json.dumps({
        "fuente": ext.fuente,
        "dataset": ext.dataset,
        "metodo": ext.metodo,
        "url": ext.url,
        "params": ext.params,
        **ext.columnas_extra,
        "fecha_extraccion": ext.fecha_extraccion.isoformat(timespec="seconds"),
        "archivo": relativa(ext.archivo),
        "sha256": ext.hash_archivo,
        "bytes": ext.archivo.stat().st_size,
        "registros": len(ext.registros),
        "resumen": ext.resumen,
        "avisos": ext.avisos,
    }, ensure_ascii=False, indent=2, default=str)
    if not destino.exists() or destino.read_text(encoding="utf-8") != texto:
        destino.write_text(texto, encoding="utf-8", newline="\n")  # LF en cualquier SO
    return destino


def rango_anios(anios) -> str:
    anios = sorted({int(a) for a in anios})
    return f"{anios[0]}-{anios[-1]}" if anios else "sin años"
