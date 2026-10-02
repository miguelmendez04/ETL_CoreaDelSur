"""KOSIS (KOSTAT): ingesta de las descargas manuales.

La OpenAPI de KOSIS está restringida a residentes de Corea, así que el equipo descarga cada tabla desde kosis.kr
y guarda el CSV en data/bronze/kosis/<AAAA-MM-DD>/. Este extractor no descarga nada: localiza la versión más
reciente de cada archivo del catálogo (config.yaml -> kosis.archivos), verifica que se pueda leer y que tenga la
estructura esperada, y devuelve sus filas tal como están para cargarlas en bronze.kosis.
"""
import logging
import re
from datetime import datetime

import pandas as pd

from src.extract.comun import Extraccion, rango_anios, sha256, version_reciente
from src.utils.config import ruta

FUENTE = "KOSIS"
CARPETA = "kosis"
log = logging.getLogger("extract.kosis")


def datasets(cfg: dict) -> list[str]:
    return list(cfg["kosis"]["archivos"])


def _encabezados(raw: pd.DataFrame, formato: str) -> tuple[list[str], int]:
    """Nombres de columna y número de filas de encabezado. En encabezado doble se combinan como 'periodo | ítem'."""
    if formato == "ancho":
        nombres = [str(c).strip() for c in raw.iloc[0]]
        filas = 1
    elif formato == "encabezado_doble":
        nombres = [a.strip() if (not b.strip() or a.strip() == b.strip()) else f"{a.strip()} | {b.strip()}"
                   for a, b in zip(raw.iloc[0], raw.iloc[1])]
        filas = 2
    else:
        raise ValueError(f"formato '{formato}' no soportado (usar 'ancho' o 'encabezado_doble')")
    vistos, unicos = {}, []
    for i, n in enumerate(nombres):
        n = n or f"_columna_{i}"           # columnas sin nombre (p. ej. la vacía al final de algunas descargas)
        vistos[n] = vistos.get(n, 0) + 1
        unicos.append(n if vistos[n] == 1 else f"{n} #{vistos[n]}")
    return unicos, filas


def _periodos(raw: pd.DataFrame, nombres: list[str], formato: str, n_dims: int) -> tuple[set[int], int]:
    """Años con columnas anuales y número de columnas de otra periodicidad (meses, que se conservan en bronze)."""
    etiquetas = raw.iloc[0, n_dims:] if formato == "encabezado_doble" else pd.Series(nombres[n_dims:])
    anios, otras = set(), 0
    for e in etiquetas.astype(str).str.strip():
        m = re.fullmatch(r"(\d{4})(?: Year| 년)?", e)
        if m:
            anios.add(int(m.group(1)))
        elif re.match(r"\d{4}\.\d{2}", e):
            otras += 1
    return anios, otras


def extraer(nombre: str, cfg: dict) -> Extraccion:
    kc = cfg["kosis"]
    spec = kc["archivos"][nombre]
    archivo = version_reciente(CARPETA, spec["patron"])
    if archivo is None:
        raise FileNotFoundError(
            f"No hay ningún archivo '{spec['patron']}' en {ruta('bronze') / CARPETA}/<fecha>/. "
            f"Descargar '{spec['tabla_kosis']}' desde {kc['url_portal']} y guardarlo ahí.")
    contenido = archivo.read_bytes()
    try:
        raw = pd.read_csv(archivo, encoding=spec["encoding"], header=None, dtype=str, keep_default_na=False)
    except UnicodeDecodeError as e:
        raise ValueError(f"{archivo.name} no se puede leer como {spec['encoding']}: revisar 'encoding' en config.yaml") from e

    nombres, filas_encabezado = _encabezados(raw, spec["formato"])
    dims = spec["columnas_dimension"]
    faltan = [d for d in dims if d not in nombres[:len(dims)]]
    if faltan:
        raise ValueError(f"{archivo.name}: no se encontraron las columnas de dimensión {faltan}; "
                         f"primeros encabezados: {nombres[:len(dims) + 2]}. ¿Se descargó la tabla correcta?")
    cuerpo = raw.iloc[filas_encabezado:]
    if cuerpo.empty:
        raise ValueError(f"{archivo.name} no tiene filas de datos")
    registros = [dict(zip(nombres, fila)) for fila in cuerpo.itertuples(index=False, name=None)]

    anios, columnas_mensuales = _periodos(raw, nombres, spec["formato"], len(dims))
    esperado = spec.get("periodo_esperado")
    avisos = []
    if esperado:
        faltantes = sorted(set(range(esperado["inicio"], esperado["fin"] + 1)) - anios)
        if faltantes:
            avisos.append(f"faltan años del periodo esperado: {rango_anios(faltantes)} ({len(faltantes)})")
    vacias = int((cuerpo.iloc[:, len(dims):].apply(lambda c: c.str.strip()).isin(["", "-"])).sum().sum())

    # La fecha de extracción es la de la descarga manual: el nombre de la carpeta (AAAA-MM-DD).
    try:
        fecha = datetime.strptime(archivo.parent.name[:10], "%Y-%m-%d").astimezone()
    except ValueError:
        fecha = datetime.fromtimestamp(archivo.stat().st_mtime).astimezone()
        avisos.append(f"la carpeta '{archivo.parent.name}' no es una fecha; se usa la fecha de modificación")

    url = kc["url_tabla"].format(**spec) if spec.get("tbl_id") else kc["url_portal"]
    return Extraccion(
        fuente=FUENTE, dataset=nombre, metodo="descarga_manual", url=url,
        params={"archivo": archivo.name, "tabla_kosis": spec["tabla_kosis"], "encoding": spec["encoding"],
                "formato": spec["formato"]},
        registros=registros, archivo=archivo, hash_archivo=sha256(contenido), fecha_extraccion=fecha,
        columnas_extra={"org_id": spec.get("org_id"), "tbl_id": spec.get("tbl_id")},
        resumen={"filas": len(registros), "columnas": len(nombres), "anios": rango_anios(anios),
                 "columnas_mensuales": columnas_mensuales, "celdas_vacias": vacias},
        avisos=avisos,
    )
