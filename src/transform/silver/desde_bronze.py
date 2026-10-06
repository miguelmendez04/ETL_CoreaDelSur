"""Lectura de la capa bronze desde PostgreSQL: la última carga exitosa de cada dataset.

Silver se construye desde las tablas bronze.* (no desde los archivos) para que cada fila herede el id_carga
de la carga bronze de donde salió.
"""
from dataclasses import dataclass

import pandas as pd
import psycopg

TABLAS = {"KOSIS": "bronze.kosis", "WB": "bronze.worldbank_wdi", "OECD": "bronze.oecd_sdmx", "UNWPP": "bronze.unwpp_wpp2024"}


@dataclass
class DatasetBronze:
    fuente: str
    dataset: str
    id_carga: int
    fecha_extraccion: pd.Timestamp
    parametros: dict
    registros: pd.DataFrame      # columnas: id_bronze + una por clave del registro original (todo como texto)


def ultima_carga(conn: psycopg.Connection, fuente: str, dataset: str) -> tuple[int, dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id_carga, parametros FROM ctl.log_cargas
                       WHERE capa = 'bronze' AND fuente = %s AND dataset = %s AND estado = 'exito'
                       ORDER BY id_carga DESC LIMIT 1""", (fuente, dataset))
        fila = cur.fetchone()
    if fila is None:
        raise LookupError(f"No hay ninguna carga exitosa de {fuente}/{dataset} en bronze. Correr: python main.py --capa bronze")
    return fila[0], fila[1] or {}


def leer(conn: psycopg.Connection, fuente: str, dataset: str) -> DatasetBronze:
    id_carga, parametros = ultima_carga(conn, fuente, dataset)
    with conn.cursor() as cur:
        cur.execute(f"SELECT id_bronze, fecha_extraccion, registro FROM {TABLAS[fuente]} "
                    "WHERE dataset = %s AND id_carga = %s ORDER BY id_bronze", (dataset, id_carga))
        filas = cur.fetchall()
    registros = pd.DataFrame([r[2] for r in filas])
    registros.insert(0, "id_bronze", [r[0] for r in filas])
    return DatasetBronze(fuente, dataset, id_carga, pd.Timestamp(filas[0][1]), parametros, registros)
