"""Capa silver: bronze (última carga exitosa de cada dataset) -> silver.* + ctl.rechazos + data/silver/.

Pasos:
  1. leer bronze desde PostgreSQL y pasar a formato largo (normalize.py)
  2. homologar etiquetas a códigos de las dimensiones (homologacion.py)
  3. convertir valores y unidades; validar tipo, nulos, rango, indicador y clave única (quality/validate.py)
  4. agrupar edades (85+), agregados de edad, Chungnam+Sejong y coherencia de totales
  5. indicadores derivados y estado preliminar/definitivo (derive.py)
  6. conciliación maestra vs contraste (reconcile.py)
  7. escribir silver en una transacción, registrar cada tabla en ctl.log_cargas y respaldar en data/silver/

Las filas que quedan después de cada paso se guardan en ctl.pasos_silver (embudo de la transformación) y los
registros evaluados, válidos y rechazados de cada dataset de bronze en ctl.calidad_dataset.
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

KOSIS = {"vitales_nacional": normalize.kosis_vitales_nacional,
         "vitales_sido": normalize.kosis_vitales_sido, "tfr_sido": normalize.kosis_tfr_sido,
         "eaps_sido": normalize.kosis_eaps_sido, "eaps_sexo_edad": normalize.kosis_eaps_sexo_edad,
         "poblacion_nacional": normalize.kosis_poblacion_nacional, "poblacion_sido": normalize.kosis_poblacion_sido,
         "proyeccion_escenarios": normalize.kosis_proyeccion_escenarios}


def pasos_embudo(pasos: list[tuple[str, str, int, str]]) -> pd.DataFrame:
    """(paso, tipo, filas, descripción) en orden -> tabla de ctl.pasos_silver. Los filtros anteriores al primer
    cálculo forman el embudo (siempre decreciente); después, los cálculos agregan filas."""
    df = pd.DataFrame(pasos, columns=["paso", "tipo", "filas", "descripcion"])
    df.insert(0, "orden", range(1, len(df) + 1))
    df["variacion"] = df["filas"].diff().fillna(0).astype(int)
    df["en_embudo"] = (df["tipo"] == "filtro") & (df["tipo"] == "calculo").cumsum().eq(0)
    if (df.loc[df["en_embudo"], "variacion"] > 0).any():
        raise ValueError("Un filtro de silver agregó filas: revisar el orden de los pasos")
    return df


def calidad_por_dataset(validos: pd.DataFrame, rechazos: pd.DataFrame) -> pd.DataFrame:
    """Registros evaluados, válidos y rechazados por dataset de bronze (lo fuera de alcance y los años en que el
    territorio no existía no se evalúan: no son errores)."""
    v = validos.groupby(["fuente", "dataset"]).size().rename("validos")
    reg = pd.DataFrame(list(rechazos["registro"])) if not rechazos.empty else pd.DataFrame(columns=["fuente", "dataset"])
    r = reg.groupby(["fuente", "dataset"]).size().rename("rechazados")
    out = pd.concat([v, r], axis=1).fillna(0).astype(int).reset_index()
    out = out.rename(columns={"validos": "registros_validos", "rechazados": "registros_rechazados"})
    out["registros_evaluados"] = out["registros_validos"] + out["registros_rechazados"]
    return out.sort_values(["fuente", "dataset"]).reset_index(drop=True)


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
    pasos = [("Formato largo", "filtro", len(cand), "Valores de bronze en formato largo: columnas anuales e ítems del estudio")]

    # 2-3. Homologar, convertir y validar
    df, r_homol, fuera = homologacion.homologar(cand, dims, cfg)
    pasos += [("En alcance", "filtro", len(cand) - sum(fuera.values()),
               "Sin escenarios KOSTAT no usados ni grupos de edad solapados (fuera de alcance, ver config.yaml)"),
              ("Homologados", "filtro", len(df), "Territorio, sexo, edad y escenario con código; lo demás a ctl.rechazos")]
    for col in ("edicion_proyeccion", "escenario"):   # centinela para agrupar sin perder filas del histórico
        df[col] = df[col].where(df["nivel"] == "proyeccion", "-")
    df, r_valor, no_aplica = validate.convertir_valores(df, dims)
    pasos.append(("Con dato (sin imputar)", "filtro", len(df), "Sin nulos ni años en que el territorio no existía"))
    df = validate.agrupar_edades(df)
    df, r_valid = validate.validar(df, dims)
    pasos.append(("Válidos (85+ agrupado y reglas)", "filtro", len(df),
                  "85-89 … 100+ sumados en 85+; indicador válido, rango y clave única"))

    # 4-5. Agregados, coherencia y derivados
    df = derive.agregados_edad(df, s["agregados_edad"])
    pasos.append(("+ agregados de edad", "calculo", len(df), "0-14, 15-64 y 65+ sumados desde los quinquenales"))
    validos = df.copy()
    df, r_coher = validate.coherencia_totales(df, cfg["calidad"]["tolerancia_suma_edades_pct"],
                                                 cfg["calidad"]["coherencia_totales"])
    pasos.append(("Coherencia de totales", "filtro", len(df), "Suma de edades ≈ total y H + M ≈ T (población y EAPS)"))
    df = derive.chungnam_sejong(df, s["agregado_cnsj"])
    pasos.append(("+ Chungnam + Sejong", "calculo", len(df), "Agregado territorial; tasas recalculadas desde niveles"))
    df = derive.derivados(df)
    pasos.append(("+ indicadores derivados", "calculo", len(df),
                  "% 65+, índice de envejecimiento y dependencia de vejez = filas en silver"))
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
    # válidos por dataset = los que pasaron las reglas fila a fila y no se rechazaron por coherencia de totales
    validos = validos[~validos["id_bronze"].isin(pd.DataFrame(list(r_coher["registro"]))["id_bronze"])]         if not r_coher.empty else validos
    return {"dims": dims, "hist": df[df["nivel"] == "historico"], "proy": df[df["nivel"] == "proyeccion"],
            "conc": conc, "rechazos": rechazos, "candidatos": cand, "fuera_alcance": {**fuera, "no_aplica": no_aplica},
            "pasos": pasos_embudo(pasos), "calidad_dataset": calidad_por_dataset(validos, rechazos)}


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
        carga.escribir(conn, r["dims"], hist, proy, conc, rech, r["pasos"].assign(id_carga=ids["silver.fact_historico"]),
                       r["calidad_dataset"].assign(id_carga=ids["silver.fact_historico"]))

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
        log.info("Embudo bronze -> silver:\n%s", r["pasos"][["orden", "paso", "filas", "variacion"]].to_string(index=False))
        m = archivos.exportar(conn, "silver", carga.TABLAS + ["ctl.rechazos", "ctl.pasos_silver", "ctl.calidad_dataset"], ids,
                              solo_esta_carga=("ctl.rechazos", "ctl.pasos_silver", "ctl.calidad_dataset"))
        log.info("Respaldo silver: %s (%d archivos Parquet)", m["archivos"][0]["archivo"].rsplit("/", 1)[0], len(m["archivos"]))
        return resumen
    except Exception as e:
        ctl.marcar_fallo(conn, ids, e)
        raise
    finally:
        conn.close()
