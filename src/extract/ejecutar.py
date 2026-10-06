"""Capa bronze: extrae cada dataset del catálogo (config.yaml) y lo deja en data/bronze/, bronze.* y ctl.log_cargas.

Por dataset:
  1. ctl.log_cargas  -> se abre la carga (estado 'en_curso'), así también quedan registrados los fallos.
  2. extractor       -> API o descarga manual; el crudo queda en data/bronze/<fuente>/<fecha>/.
  3. bronze.<tabla>  -> un registro por fila, sin modificar. Si el crudo es idéntico al de la última carga
                        exitosa (mismo sha256) no se duplica: la carga queda 'omitido' (salvo --forzar).
  4. metadata        -> <archivo>_metadata.json junto al crudo, con url, parámetros, hash y resumen
                        (describe el archivo; la carga se busca en ctl.log_cargas por archivo o hash).
"""
import logging
import time

import pandas as pd

from src.extract import kosis, oecd, unwpp, worldbank
from src.extract.comun import escribir_metadata, relativa
from src.load import bronze as carga
from src.utils.config import cargar_config
from src.utils.db import conectar

EXTRACTORES = {"worldbank": worldbank, "oecd": oecd, "unwpp": unwpp, "kosis": kosis}
log = logging.getLogger("bronze")


def catalogo(fuentes: list[str] | None = None) -> pd.DataFrame:
    """Lista de datasets que se pueden extraer, leída de config.yaml."""
    cfg = cargar_config()
    filas = []
    for clave, modulo in EXTRACTORES.items():
        if fuentes and clave not in fuentes:
            continue
        for ds in modulo.datasets(cfg):
            filas.append({"fuente": clave, "dataset": ds, "metodo": cfg[clave].get("metodo_extraccion"),
                          "tabla_bronze": cfg[clave]["tabla_bronze"]})
    return pd.DataFrame(filas)


def ejecutar_bronze(fuentes: list[str] | None = None, datasets: list[str] | None = None,
                    usar_db: bool = True, forzar: bool = False) -> pd.DataFrame:
    cfg = cargar_config()
    tareas = catalogo(fuentes)
    if datasets:
        desconocidos = set(datasets) - set(tareas["dataset"])
        if desconocidos:
            raise ValueError(f"Datasets que no están en el catálogo{' de ' + ', '.join(fuentes) if fuentes else ''}: "
                             f"{sorted(desconocidos)}. Ver la lista con: python main.py --listar")
        tareas = tareas[tareas["dataset"].isin(datasets)]

    conn = conectar() if usar_db else None
    resultados = []
    log.info("Capa bronze: %d datasets (%s)%s", len(tareas), ", ".join(tareas["fuente"].unique()),
             "" if usar_db else " [sin base de datos: solo archivos]")
    try:
        for t in tareas.itertuples():
            resultados.append(_procesar(t, cfg, conn, forzar))
    finally:
        if conn is not None:
            conn.close()

    resumen = pd.DataFrame(resultados)
    log.info("Resumen capa bronze:\n%s", resumen.drop(columns=["detalle"]).to_string(index=False))
    for r in resultados:
        if r["detalle"]:
            log.info("  %s/%s: %s", r["fuente"], r["dataset"], r["detalle"])
    return resumen


def _procesar(t, cfg: dict, conn, forzar: bool) -> dict:
    modulo = EXTRACTORES[t.fuente]
    inicio = time.perf_counter()
    fila = {"fuente": t.fuente, "dataset": t.dataset, "estado": None, "registros": None, "id_carga": None,
            "archivo": None, "seg": None, "detalle": ""}
    log.info("[%s] %s ...", t.fuente, t.dataset)
    id_carga = carga.abrir_carga(conn, modulo.FUENTE, t.dataset, t.metodo) if conn else None
    try:
        ext = modulo.extraer(t.dataset, cfg)
        fila.update(registros=len(ext.registros), archivo=relativa(ext.archivo))
        if ext.avisos:
            fila["detalle"] = "; ".join(ext.avisos)
            for a in ext.avisos:
                log.warning("  aviso: %s", a)

        if conn is None:
            estado = "solo_archivo"
        else:
            previa = None if forzar else carga.carga_identica(conn, ext)
            if previa:
                estado = "omitido"
                mensaje = f"sin cambios: crudo idéntico al de id_carga {previa}"
                carga.cerrar_carga(conn, id_carga, estado, ext, filas=0, mensaje=mensaje)
                fila["detalle"] = "; ".join(filter(None, [mensaje, fila["detalle"]]))
            else:
                n = carga.insertar_registros(conn, cfg[t.fuente]["tabla_bronze"], id_carga, ext)
                estado = "exito"
                carga.cerrar_carga(conn, id_carga, estado, ext, filas=n)
        escribir_metadata(ext)
        fila["estado"] = estado
        log.info("  %s: %d registros, %s -> %s", estado, len(ext.registros), ext.resumen, relativa(ext.archivo))
    except Exception as e:  # cualquier fallo queda en ctl.log_cargas y no detiene los demás datasets
        if conn is not None:
            conn.rollback()
            carga.cerrar_carga(conn, id_carga, "fallo", mensaje=f"{type(e).__name__}: {e}")
        fila.update(estado="fallo", detalle=f"{type(e).__name__}: {e}")
        log.error("  fallo: %s: %s", type(e).__name__, e)
    fila.update(id_carga=id_carga, seg=round(time.perf_counter() - inicio, 1))
    return fila
