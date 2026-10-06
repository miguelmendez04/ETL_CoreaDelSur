"""Escritura en PostgreSQL de la capa bronze y de la bitácora ctl.log_cargas."""
import json

import psycopg
from psycopg import sql

from src.extract.comun import Extraccion, hash_registro, relativa
from src.load import ctl

# Columnas propias de cada tabla bronze, además de las comunes.
COLUMNAS_EXTRA = {"bronze.kosis": ["org_id", "tbl_id"]}
COLUMNAS_COMUNES = ["id_carga", "fuente", "dataset", "url", "params", "fecha_extraccion", "registro", "hash_registro"]


def _tabla(nombre: str) -> sql.Composed:
    esquema, tabla = nombre.split(".")
    return sql.Identifier(esquema, tabla)


def abrir_carga(conn: psycopg.Connection, fuente: str, dataset: str, metodo: str) -> int:
    return ctl.abrir_carga(conn, "bronze", dataset, fuente=fuente, metodo=metodo)


def carga_identica(conn: psycopg.Connection, ext: Extraccion) -> int | None:
    """id_carga de la última carga exitosa del mismo dataset con exactamente el mismo crudo (mismo sha256)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id_carga FROM ctl.log_cargas
                       WHERE capa = 'bronze' AND fuente = %s AND dataset = %s AND estado = 'exito' AND hash_archivo = %s
                       ORDER BY id_carga DESC LIMIT 1""", (ext.fuente, ext.dataset, ext.hash_archivo))
        fila = cur.fetchone()
    return fila[0] if fila else None


def insertar_registros(conn: psycopg.Connection, tabla: str, id_carga: int, ext: Extraccion) -> int:
    """Inserta un registro por fila con COPY (rápido incluso para los ~150 mil registros de UN WPP)."""
    extra = COLUMNAS_EXTRA.get(tabla, [])
    columnas = sql.SQL(", ").join(map(sql.Identifier, COLUMNAS_COMUNES + extra))
    params = json.dumps(ext.params, ensure_ascii=False)
    valores_extra = [ext.columnas_extra.get(c) for c in extra]
    with conn.cursor() as cur:
        with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(_tabla(tabla), columnas)) as copia:
            for r in ext.registros:
                copia.write_row([id_carga, ext.fuente, ext.dataset, ext.url, params, ext.fecha_extraccion,
                                 json.dumps(r, ensure_ascii=False, allow_nan=False), hash_registro(r), *valores_extra])
    return len(ext.registros)


def cerrar_carga(conn: psycopg.Connection, id_carga: int, estado: str, ext: Extraccion | None = None,
                 filas: int | None = None, mensaje: str | None = None) -> None:
    parametros = None
    if ext is not None:
        parametros = json.dumps({"url": ext.url, **ext.params, **ext.columnas_extra, "resumen": ext.resumen,
                                 "avisos": ext.avisos}, ensure_ascii=False, default=str)
    with conn.cursor() as cur:
        cur.execute("""UPDATE ctl.log_cargas
                       SET fin = now(), estado = %s, filas_extraidas = %s, mensaje_error = %s,
                           parametros = COALESCE(%s::jsonb, parametros),
                           archivo = COALESCE(%s, archivo), hash_archivo = COALESCE(%s, hash_archivo)
                       WHERE id_carga = %s""",
                    (estado, filas, mensaje, parametros,
                     relativa(ext.archivo) if ext else None, ext.hash_archivo if ext else None, id_carga))
    conn.commit()
