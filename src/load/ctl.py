"""Bitácora del pipeline (esquema ctl) y escritura masiva con COPY, comunes a las tres capas."""
import json

import pandas as pd
import psycopg
from psycopg import sql


def abrir_carga(conn: psycopg.Connection, capa: str, dataset: str, fuente: str = "PIPELINE",
                metodo: str = "pipeline", parametros: dict | None = None) -> int:
    """Registra el inicio de una carga ('en_curso') y la confirma de inmediato: si después algo falla, el intento
    queda en la bitácora."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO ctl.log_cargas (capa, fuente, dataset, metodo, parametros)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id_carga""",
                    (capa, fuente, dataset, metodo,
                     json.dumps(parametros, ensure_ascii=False, default=str) if parametros else None))
        id_carga = cur.fetchone()[0]
    conn.commit()
    return id_carga


def cerrar_carga(conn: psycopg.Connection, id_carga: int, estado: str, extraidas=None, validas=None, rechazadas=None,
                 mensaje=None) -> None:
    with conn.cursor() as cur:
        cur.execute("""UPDATE ctl.log_cargas SET fin = now(), estado = %s, filas_extraidas = %s, filas_validas = %s,
                       filas_rechazadas = %s, mensaje_error = %s WHERE id_carga = %s""",
                    (estado, extraidas, validas, rechazadas, mensaje, id_carga))
    conn.commit()


def marcar_fallo(conn: psycopg.Connection, ids: dict[str, int], error: Exception) -> None:
    conn.rollback()
    for id_carga in ids.values():
        cerrar_carga(conn, id_carga, "fallo", mensaje=f"{type(error).__name__}: {error}")


def copiar(cur: psycopg.Cursor, tabla: str, df: pd.DataFrame, columnas: list[str]) -> None:
    """Inserta un DataFrame con COPY (rápido para decenas de miles de filas). NaN -> NULL."""
    datos = df[columnas].astype(object).where(df[columnas].notna(), None)
    destino = sql.Identifier(*tabla.split("."))
    with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(destino, sql.SQL(", ").join(map(sql.Identifier, columnas)))) as cp:
        for fila in datos.itertuples(index=False, name=None):
            cp.write_row(fila)


def leer_tabla(conn: psycopg.Connection, tabla: str, ids_carga: list[int] | None = None) -> pd.DataFrame:
    """SELECT * de una tabla o vista como DataFrame (NUMERIC -> float; id_* -> entero que admite nulos).
    Con ids_carga solo trae las filas de esas cargas."""
    consulta = sql.SQL("SELECT * FROM {}").format(sql.Identifier(*tabla.split(".")))
    if ids_carga is not None:
        consulta += sql.SQL(" WHERE id_carga = ANY(%s)")
    with conn.cursor() as cur:
        cur.execute(consulta, (list(ids_carga),) if ids_carga is not None else None)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    for col in df.columns:
        if df[col].map(type).astype(str).str.contains("Decimal").any():
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if col.startswith("id_") and col != "id_supuesto":
            df[col] = df[col].astype("Int64")
    return df
