"""Conexión a PostgreSQL con las variables PG_* de .env."""
import os

import psycopg

from src.utils.config import cargar_config


def conectar() -> psycopg.Connection:
    cargar_config()  # asegura que .env esté cargado
    return psycopg.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        connect_timeout=5,
    )
