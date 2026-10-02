"""Configuración del proyecto: config/config.yaml + variables de entorno (.env)."""
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def cargar_config() -> dict:
    load_dotenv(RAIZ / ".env")
    with open(RAIZ / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ruta(clave: str) -> Path:
    """Ruta absoluta de una entrada de `rutas` en config.yaml (bronze, silver, gold, logs, mappings)."""
    return RAIZ / cargar_config()["rutas"][clave]
