"""Logging del pipeline: consola + logs/pipeline.log."""
import logging

from src.utils.config import RAIZ, cargar_config


def configurar_logging() -> None:
    cfg = cargar_config()["logging"]
    archivo = RAIZ / cfg["archivo"]
    archivo.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=cfg["nivel"],
        format="%(asctime)s %(levelname)-7s %(name)s - %(message)s",
        handlers=[logging.FileHandler(archivo, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )
    # urllib3 registra cada reintento en DEBUG/WARNING; el extractor ya lo informa.
    logging.getLogger("urllib3").setLevel(logging.ERROR)
