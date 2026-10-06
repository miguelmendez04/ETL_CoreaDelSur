"""Respaldo en archivos de las capas silver y gold: data/<capa>/<AAAA-MM-DD>/.

PostgreSQL es la fuente de verdad; estos archivos son una foto de lo que quedó cargado, para:
  - silver: respaldo limpio en Parquet (se puede analizar sin la base, p. ej. desde un notebook);
  - gold: datos de negocio en Parquet y CSV (Power BI, Excel o una futura API sin conectarse a la base).
Se leen de la base después de confirmar la carga, así coinciden con lo que ve Power BI. Una carpeta por día:
si se corre dos veces el mismo día, la foto se reemplaza (silver y gold se reconstruyen desde bronze).
"""
import hashlib
import json
from datetime import datetime

import psycopg

from src.load.ctl import leer_tabla
from src.utils.config import RAIZ, ruta


def exportar(conn: psycopg.Connection, capa: str, tablas: list[str], ids_carga: dict[str, int],
             csv: bool = False, solo_esta_carga: tuple[str, ...] = ()) -> dict:
    """solo_esta_carga: tablas de historial (p. ej. ctl.rechazos) de las que se exportan solo las filas de esta
    ejecución."""
    carpeta = ruta(capa) / datetime.now().strftime("%Y-%m-%d")
    carpeta.mkdir(parents=True, exist_ok=True)
    manifiesto = {"capa": capa, "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
                  "ids_carga": ids_carga, "archivos": []}
    for tabla in tablas:
        df = leer_tabla(conn, tabla, list(ids_carga.values()) if tabla in solo_esta_carga else None)
        for col in df.columns:   # JSONB / listas -> texto para que Parquet y CSV los acepten
            if df[col].map(lambda v: isinstance(v, (dict, list))).any():
                df[col] = df[col].map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
        nombre = tabla.split(".")[1]
        destinos = [carpeta / f"{nombre}.parquet"]
        df.to_parquet(destinos[0], index=False)
        if csv:
            destinos.append(carpeta / f"{nombre}.csv")
            df.to_csv(destinos[1], index=False, encoding="utf-8-sig")
        for d in destinos:
            manifiesto["archivos"].append({"tabla": tabla, "archivo": d.relative_to(RAIZ).as_posix(), "filas": len(df),
                                          "columnas": list(df.columns),
                                          "sha256": hashlib.sha256(d.read_bytes()).hexdigest()})
    (carpeta / "manifest.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return manifiesto
