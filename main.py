"""Orquestación del pipeline ETL (arquitectura medallón): bronze -> silver (-> gold en el siguiente avance).

Uso:
    python main.py --listar                          # catálogo de datasets por fuente (desde config.yaml)
    python main.py                                   # capa bronze, todas las fuentes
    python main.py --capa bronze --fuente oecd       # una fuente
    python main.py --dataset SP.POP.TOTL tfr_sido    # datasets puntuales
    python main.py --sin-db                          # solo archivos crudos, sin PostgreSQL
    python main.py --forzar                          # recarga en bronze aunque el crudo no haya cambiado
"""
import argparse
import logging
import sys

import psycopg

from src.extract.ejecutar import EXTRACTORES, catalogo, ejecutar_bronze
from src.utils.logs import configurar_logging

CAPAS = ["bronze", "silver"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline ETL Corea del Sur (medallón)")
    parser.add_argument("--capa", choices=CAPAS, default="bronze", help="capa a construir (por defecto bronze)")
    parser.add_argument("--fuente", nargs="+", choices=list(EXTRACTORES), help="una o varias fuentes")
    parser.add_argument("--dataset", nargs="+", help="uno o varios datasets del catálogo")
    parser.add_argument("--sin-db", action="store_true", help="no escribir en PostgreSQL (solo data/bronze)")
    parser.add_argument("--forzar", action="store_true", help="cargar aunque el crudo sea idéntico al último")
    parser.add_argument("--listar", action="store_true", help="mostrar el catálogo de datasets y salir")
    args = parser.parse_args()

    if args.listar:
        print(catalogo(args.fuente).to_string(index=False))
        return 0

    configurar_logging()
    log = logging.getLogger("pipeline")

    if args.capa == "silver":
        log.info("Capa silver: pendiente de implementar (transformación del Avance 2).")
        return 0

    try:
        resumen = ejecutar_bronze(args.fuente, args.dataset, usar_db=not args.sin_db, forzar=args.forzar)
    except ValueError as e:
        log.error(str(e))
        return 2
    except psycopg.OperationalError as e:
        log.error("No hay conexión a PostgreSQL (%s). Levantarlo con 'docker compose up -d' "
                  "o ejecutar con --sin-db para solo descargar los archivos.", str(e).strip().splitlines()[0])
        return 1
    return 1 if (resumen["estado"] == "fallo").any() else 0


if __name__ == "__main__":
    sys.exit(main())
