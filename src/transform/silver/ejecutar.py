"""Capa silver: bronze (última carga exitosa de cada dataset) -> silver.* + ctl.rechazos + data/silver/.

Pasos:
  1. leer bronze desde PostgreSQL y pasar a formato largo (normalize.py)
  2. homologar etiquetas a códigos de las dimensiones (homologacion.py)
  3. convertir valores y unidades; validar tipo, nulos, rango, indicador y clave única (quality/validate.py)
  4. agrupar edades (85+), agregados de edad, Chungnam+Sejong y coherencia de totales
  5. indicadores derivados y estado preliminar/definitivo (derive.py)
  6. conciliación maestra vs contraste (reconcile.py)
  7. escribir silver en una transacción, registrar cada tabla en ctl.log_cargas y respaldar en data/silver/
"""
import logging
import time

import pandas as pd

from src.load import archivos, ctl
from src.load import silver as carga
from src.quality import validate
from src.transform.silver import derive, homologacion, normalize, reconcile
from src.transform.silver.desde_bronze import leer
from src.utils.config import cargar_config
from src.utils.db import conectar

log = logging.getLogger("silver")

KOSIS = {"vitales_sido": normalize.kosis_vitales_sido, "tfr_sido": normalize.kosis_tfr_sido,
         "eaps_sido": normalize.kosis_eaps_sido, "eaps_sexo_edad": normalize.kosis_eaps_sexo_edad,
         "poblacion_nacional": normalize.kosis_poblacion_nacional, "poblacion_sido": normalize.kosis_poblacion_sido,
         "proyeccion_escenarios": normalize.kosis_proyeccion_escenarios}


def construir(conn, cfg: dict) -> dict:
    """Todo el cálculo de silver, sin escribir en la base. Devuelve los DataFrames y métricas."""
    s = cfg["silver"]
    dims = homologacion.cargar_dimensiones()

    # 1. Bronze -> largo
    partes, bronze = [], {}
    for ds, funcion in KOSIS.items():
        bronze[ds] = leer(conn, "KOSIS", ds)
        partes.append(funcion(bronze[ds], cfg))
    wb = {cod: leer(conn, "WB", cod) for cod in cfg["worldbank"]["datasets"]}
    maestra = dict(zip(dims["indicador"]["cod_indicador"], dims["indicador"]["fuente_maestra"]))
    partes += [normalize.worldbank(wb[cod], cfg, regla, incluir_kor=maestra.get(regla["indicador"]) == "WB")
               for cod, regla in s["worldbank_historico"].items()]
    oecd = {ds: leer(conn, "OECD", ds) for ds in ("productividad", "fecundidad_nacimientos", "fuerza_laboral",
                                                   "participacion_edad_sexo")}
    partes.append(normalize.oecd_productividad(oecd["productividad"], cfg))
    partes.append(normalize.oecd_participacion(oecd["participacion_edad_sexo"], cfg))
    cand = pd.concat(partes, ignore_index=True)
    log.info("  candidatos: %d valores desde %d datasets de bronze", len(cand), len(partes))

    # 2-3. Homologar, convertir y validar
    df, r_homol, fuera = homologacion.homologar(cand, dims, cfg)
    for col in ("edicion_proyeccion", "escenario"):   # centinela para agrupar sin perder filas del histórico
        df[col] = df[col].where(df["nivel"] == "proyeccion", "-")
    df, r_valor, no_aplica = validate.convertir_valores(df, dims)
    df = validate.agrupar_edades(df)
    df, r_valid = validate.validar(df, dims)

    # 4-5. Agregados, coherencia y derivados
    df = derive.agregados_edad(df, s["agregados_edad"])
    df, r_coher = validate.coherencia_totales(df, cfg["calidad"]["tolerancia_suma_edades_pct"],
                                                 cfg["calidad"]["coherencia_totales"])
    df = derive.chungnam_sejong(df, s["agregado_cnsj"])
    df = derive.derivados(df)
    df["estado"] = derive.estado(df, s["preliminar"])

    # 6. Conciliación
    variantes = {v: e for v, e in [("Median", "medio"), ("High-fertility", "alto"), ("Low-fertility", "bajo")]}
    contrastes = pd.concat([
        reconcile.contraste_worldbank(wb),
        reconcile.contraste_oecd(oecd["fecundidad_nacimientos"], oecd["fuerza_laboral"]),
        reconcile.contraste_unwpp(leer(conn, "UNWPP", "poblacion_edad_sexo"), variantes, s["periodo_historico_hasta"],
                                  s["agregados_edad"]),
    ], ignore_index=True)
    conc = reconcile.conciliar(df, contrastes)

    rechazos = pd.concat([r_homol, r_valor, r_valid, r_coher], ignore_index=True)
    return {"dims": dims, "hist": df[df["nivel"] == "historico"], "proy": df[df["nivel"] == "proyeccion"],
            "conc": conc, "rechazos": rechazos, "candidatos": cand, "fuera_alcance": {**fuera, "no_aplica": no_aplica}}


def ejecutar_silver() -> pd.DataFrame:
    cfg = cargar_config()
    inicio = time.perf_counter()
    conn = conectar()
    ids = {}
    try:
        log.info("Capa silver: reconstrucción completa desde bronze")
        ids = {t: ctl.abrir_carga(conn, "silver", t, parametros={"tolerancia_conciliacion_pct": cfg["calidad"]["tolerancia_conciliacion_pct"]})
               for t in ("silver.fact_historico", "silver.fact_proyeccion", "silver.conciliacion")}
        r = construir(conn, cfg)
        hist, proy, conc, rech = r["hist"].copy(), r["proy"].copy(), r["conc"].copy(), r["rechazos"].copy()
        hist["id_carga"], proy["id_carga"], conc["id_carga"] = ids["silver.fact_historico"], ids["silver.fact_proyeccion"], ids["silver.conciliacion"]
        rech["id_carga"] = rech["destino"].map(ids)
        carga.escribir(conn, r["dims"], hist, proy, conc, rech)

        resumen = []
        for tabla, datos in (("silver.fact_historico", hist), ("silver.fact_proyeccion", proy), ("silver.conciliacion", conc)):
            n_rech = int((rech["destino"] == tabla).sum())
            ctl.cerrar_carga(conn, ids[tabla], "exito", len(datos) + n_rech, len(datos), n_rech)
            resumen.append({"tabla": tabla, "id_carga": ids[tabla], "filas": len(datos), "rechazadas": n_rech,
                            "tasa_rechazo_pct": round(n_rech / max(len(datos) + n_rech, 1) * 100, 2)})
        resumen = pd.DataFrame(resumen)
        log.info("Resumen capa silver (%.1fs):\n%s", time.perf_counter() - inicio, resumen.to_string(index=False))
        if not rech.empty:
            log.info("Rechazos por regla:\n%s", rech.groupby(["destino", "regla"]).size().to_string())
        log.info("Fuera de alcance (documentado en config.yaml, no son rechazos): %s", r["fuera_alcance"])
        dentro = (conc["dif_pct"].abs() <= cfg["calidad"]["tolerancia_conciliacion_pct"])
        h = conc["nivel"] == "historico"
        log.info("Conciliación histórica: %d de %d pares dentro de ±%s%% (%.1f%%)", dentro[h].sum(), h.sum(),
                 cfg["calidad"]["tolerancia_conciliacion_pct"], dentro[h].mean() * 100)
        m = archivos.exportar(conn, "silver", carga.TABLAS + ["ctl.rechazos"], ids, solo_esta_carga=("ctl.rechazos",))
        log.info("Respaldo silver: %s (%d archivos Parquet)", m["archivos"][0]["archivo"].rsplit("/", 1)[0], len(m["archivos"]))
        return resumen
    except Exception as e:
        ctl.marcar_fallo(conn, ids, e)
        raise
    finally:
        conn.close()
