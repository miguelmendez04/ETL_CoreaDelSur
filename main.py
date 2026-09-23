"""Orquestación del pipeline ETL: extract -> bronze -> silver (-> gold en el siguiente avance).

Uso:
    python main.py                      # todas las etapas y fuentes
    python main.py --etapa extract      # solo extracción
    python main.py --fuente worldbank   # una sola fuente
"""

import argparse
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent
FUENTES = ["worldbank", "kosis", "oecd", "unwpp"]
ETAPAS = ["extract", "transform", "load"]


def cargar_config() -> dict:
    with open(RAIZ / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def configurar_logging(config: dict) -> None:
    archivo = RAIZ / config["logging"]["archivo"]
    archivo.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=config["logging"]["nivel"],
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[logging.FileHandler(archivo, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline ETL Corea del Sur")
    parser.add_argument("--etapa", choices=ETAPAS, help="ejecutar solo una etapa")
    parser.add_argument("--fuente", choices=FUENTES, help="ejecutar solo una fuente")
    args = parser.parse_args()

    load_dotenv(RAIZ / ".env")
    config = cargar_config()
    configurar_logging(config)
    log = logging.getLogger("pipeline")

    etapas = [args.etapa] if args.etapa else ETAPAS
    fuentes = [args.fuente] if args.fuente else FUENTES

    for etapa in etapas:
        for fuente in fuentes:
            # TODO: conectar con src/extract, src/transform, src/quality y src/load
            log.info("Etapa %s - fuente %s: pendiente de implementar", etapa, fuente)


if __name__ == "__main__":
    main()
