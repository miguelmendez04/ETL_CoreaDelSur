"""Orquestación del pipeline ETL (arquitectura medallón): bronze -> silver -> gold.

Uso:
    python main.py                                   # pipeline completo: bronze -> silver -> gold
    python main.py --listar                          # catálogo de datasets por fuente (desde config.yaml)
    python main.py --capa bronze                     # solo extracción, todas las fuentes
    python main.py --capa bronze --fuente oecd       # una fuente
    python main.py --dataset SP.POP.TOTL tfr_sido    # datasets puntuales
    python main.py --sin-db                          # solo archivos crudos, sin PostgreSQL
    python main.py --forzar                          # recarga en bronze aunque el crudo no haya cambiado
    python main.py --capa silver                     # transforma bronze -> silver (reconstrucción completa)
    python main.py --capa gold                       # escenarios, riesgo por si-do y KPIs desde silver
"""
import argparse
import logging
import sys

import psycopg

from src.extract.ejecutar import EXTRACTORES, catalogo, ejecutar_bronze
from src.transform.gold.ejecutar import ejecutar_gold
from src.transform.silver.ejecutar import ejecutar_silver
from src.utils.logs import configurar_logging

CAPAS = ["bronze", "silver", "gold", "todas"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline ETL Corea del Sur (medallón)")
    parser.add_argument("--capa", choices=CAPAS, default="todas", help="capa a construir (por defecto todas, en orden)")
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

    try:
        if args.capa in ("bronze", "todas"):
            resumen = ejecutar_bronze(args.fuente, args.dataset, usar_db=not args.sin_db, forzar=args.forzar)
            if (resumen["estado"] == "fallo").any():
                log.error("Hubo fallos en bronze (ver resumen y ctl.log_cargas); silver y gold no se ejecutan.")
                return 1
            if args.capa == "bronze" or args.sin_db or args.fuente or args.dataset:
                return 0   # extracción parcial: silver se reconstruye con todas las fuentes, se corre aparte
        if args.capa in ("silver", "todas"):
            ejecutar_silver()
        if args.capa in ("gold", "todas"):
            ejecutar_gold()
        return 0
    except (ValueError, LookupError) as e:
        log.error(str(e))
        return 2
    except psycopg.OperationalError as e:
        log.error("No hay conexión a PostgreSQL (%s). Levantarlo con 'docker compose up -d' "
                  "o ejecutar con --sin-db para solo descargar los archivos.", str(e).strip().splitlines()[0])
        return 1


if __name__ == "__main__":
    sys.exit(main())
