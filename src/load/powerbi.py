"""Modelo semántico (TMDL) del tablero de Power BI sobre la capa de servicio data/gold/powerbi/pbi_*.parquet.

El reporte (powerbi/Tablero_ETL_Corea_Grupo6.Report: portada + 7 páginas, imágenes y tema) es el diseño del equipo
(Angie Rodríguez) y está versionado tal cual. Este módulo escribe el modelo que lo alimenta: una tabla por archivo
de la capa de servicio, las medidas DAX que usan los visuales y las relaciones por año y territorio.

Uso:
    python -m src.load.powerbi     # regenera powerbi/Tablero_ETL_Corea_Grupo6.SemanticModel y el .pbip

Solo hace falta volver a correrlo si cambian las columnas de la capa de servicio; si cambian los datos basta con
"Actualizar" en Power BI Desktop. La carpeta de la capa gold es el parámetro RutaGold (Transformar datos > Parámetros).
"""
import json
import shutil
import uuid
from pathlib import Path

import pandas as pd

from src.utils.config import RAIZ, ruta

NOMBRE = "Tablero_ETL_Corea_Grupo6"
DESTINO = RAIZ / "powerbi"
F_M = '#,0.0" M"'

# medidas por tabla: (nombre, expresión DAX, formato, descripción)
MEDIDAS = {
    "pbi_nacional": [
        ("Fecundidad (TFR)", "SUM(pbi_nacional[TFR])", "0.00", "Tasa global de fecundidad (observado, KOSIS)"),
        ("Nivel de reemplazo", "IF(NOT ISBLANK([Fecundidad (TFR)]), 2.1)", "0.0", "Referencia demográfica: 2,1 hijos por mujer"),
        ("Nacimientos (miles)", "DIVIDE(SUM(pbi_nacional[NACIMIENTOS]), 1000)", "#,0", "Nacidos vivos (observado)"),
        ("Defunciones (miles)", "DIVIDE(SUM(pbi_nacional[DEFUNCIONES]), 1000)", "#,0", "Defunciones (observado)"),
        ("Esperanza de vida", "SUM(pbi_nacional[ESPERANZA_VIDA])", "0.0", "Años (observado)"),
        ("% 0-14", "SUM(pbi_nacional[PROP_0_14])", "0.0", "Estimado ≤2022 · proyección KOSTAT medio ≥2023"),
        ("% 15-64", "SUM(pbi_nacional[PROP_15_64])", "0.0", "Estimado ≤2022 · proyección KOSTAT medio ≥2023"),
        ("% 65+", "SUM(pbi_nacional[PROP_65MAS])", "0.0", "Estimado ≤2022 · proyección KOSTAT medio ≥2023"),
        ("Dependencia de vejez · estimada",
         'CALCULATE(SUM(pbi_nacional[DEP_VEJEZ]), pbi_nacional[tipo_dato_poblacion] = "estimado")', "0.0",
         "P65+/P15-64×100 sobre población estimada (≤2022), calculada en el pipeline"),
        ("Dependencia de vejez · proyección", "CALCULATE(SUM(pbi_nacional[DEP_VEJEZ]), pbi_nacional[anio] >= 2022)", "0.0",
         "Proyección oficial KOSTAT (escenario medio) desde 2023; arranca en 2022"),
        ("Población 15-64 · estimada",
         'CALCULATE(DIVIDE(SUM(pbi_nacional[POB_15_64]), 1e6), pbi_nacional[tipo_dato_poblacion] = "estimado")', F_M, ""),
        ("Población 15-64 · proyección", "CALCULATE(DIVIDE(SUM(pbi_nacional[POB_15_64]), 1e6), pbi_nacional[anio] >= 2022)", F_M, ""),
        ("Reemplazo laboral · estimado",
         'CALCULATE(SUM(pbi_nacional[IND_REEMPLAZO_LABORAL]), pbi_nacional[tipo_dato_poblacion] = "estimado")', "0",
         "Jóvenes 15-24 por cada 100 personas de 55-64"),
        ("Reemplazo laboral · proyección", "CALCULATE(SUM(pbi_nacional[IND_REEMPLAZO_LABORAL]), pbi_nacional[anio] >= 2022)", "0", ""),
        ("Referencia 100", "IF(NOT ISBLANK([Reemplazo laboral · estimado]) || NOT ISBLANK([Reemplazo laboral · proyección]), 100)", "0", ""),
        ("Población activa observada", "DIVIDE(SUM(pbi_nacional[POB_ACTIVA]), 1e6)", F_M, "EAPS, promedio anual"),
        ("PIB por hora", "SUM(pbi_nacional[PIB_HORA])", "0.0", "USD PPA constantes (OECD)"),
        ("Participación laboral 15+", "SUM(pbi_nacional[TASA_PARTICIPACION])", "0.0", "EAPS (observado)"),
    ],
    "pbi_kpi": [(f"KPI {c}", f'CALCULATE(MAX(pbi_kpi[valor]), pbi_kpi[codigo] = "{c}")', fmt, d) for c, fmt, d in [
        ("KPI-01", "0.00", "Fecundidad (hijos por mujer)"), ("KPI-02", '0.0" %"', "Nacimientos vs 2000"),
        ("KPI-03", "#,0", "Crecimiento natural"), ("KPI-04", "0.0", "Esperanza de vida"), ("KPI-05", '0.0" %"', "Población 65+"),
        ("KPI-06", "0.0", "Dependencia de vejez 2025"), ("KPI-07", '0.0" %"', "Población 15-64 a 2050"),
        ("KPI-08", "0", "Reemplazo laboral"), ("KPI-09", '0.0" %"', "Participación 15+"), ("KPI-10", '0.0" pp"', "Brecha de género"),
        ("KPI-11", '0.0" %"', "Fuerza laboral potencial a 2050"), ("KPI-12", "0", "Si-do en riesgo alto"),
        ("KPI-13", '0.0" pp"', "Efecto de la migración en la población 15-64 a 2050"), ("KPI-14", "0.0", "PIB por hora")]],
    "pbi_escenarios": [
        ("Población 15-64 por escenario",
         'CALCULATE(SUM(pbi_escenarios[valor]), pbi_escenarios[indicador] = "Población 15-64 (millones)")', F_M,
         "Proyección oficial KOSTAT; 2025 = año base observado"),
        ("Dependencia por escenario", 'CALCULATE(SUM(pbi_escenarios[valor]), pbi_escenarios[indicador] = "Dependencia de vejez")',
         "0.0", "Proyección oficial KOSTAT"),
    ],
    "pbi_flp": [
        ("Fuerza laboral potencial",
         'VAR e = SELECTEDVALUE(pbi_escenario_sel[escenario], "Medio (base)") RETURN '
         'CALCULATE(DIVIDE(SUM(pbi_flp[flp]), 1e6), pbi_flp[escenario] = e)', F_M,
         "Escenario propio (no es pronóstico): población KOSTAT × cobertura EAPS × tasa de participación supuesta"),
        ("Índice FLP (2025 = 100)",
         'VAR e = SELECTEDVALUE(pbi_escenario_sel[escenario], "Medio (base)") RETURN '
         'CALCULATE(AVERAGE(pbi_flp[indice_2025]), pbi_flp[escenario] = e)', "0.0", ""),
        ("Escenario seleccionado", 'SELECTEDVALUE(pbi_escenario_sel[escenario], "Medio (base)")', "", ""),
    ],
    "pbi_piramide": [
        ("Hombres (%)", 'VAR a = SELECTEDVALUE(pbi_anio_sel[anio_piramide], 2025) RETURN '
                        '-CALCULATE(SUM(pbi_piramide[pct]), pbi_piramide[sexo] = "Hombres", pbi_piramide[anio] = a)',
         '0.0;0.0', "% de la población total del año (se grafica a la izquierda)"),
        ("Mujeres (%)", 'VAR a = SELECTEDVALUE(pbi_anio_sel[anio_piramide], 2025) RETURN '
                        'CALCULATE(SUM(pbi_piramide[pct]), pbi_piramide[sexo] = "Mujeres", pbi_piramide[anio] = a)', "0.0", ""),
        ("Año de la pirámide", 'VAR a = SELECTEDVALUE(pbi_anio_sel[anio_piramide], 2025) RETURN '
                               'a & IF(a <= 2022, " · estimada", " · proyección KOSTAT medio")', "", ""),
    ],
    "pbi_participacion": [
        ("Participación 2025", "CALCULATE(AVERAGE(pbi_participacion[tasa]), pbi_participacion[anio] = 2025)", "0.0", ""),
        ("Participación mujeres", 'CALCULATE(AVERAGE(pbi_participacion[tasa]), pbi_participacion[sexo] = "Mujeres")', "0.0", ""),
    ],
    "pbi_riesgo": [
        ("Índice de riesgo", "AVERAGE(pbi_riesgo[indice_riesgo])", "0.0",
         "Inferencia propia: 4 componentes normalizados 0-100 con igual peso (100 = mayor riesgo)"),
        ("Si-do en riesgo alto", 'CALCULATE(COUNTROWS(pbi_riesgo), pbi_riesgo[nivel_riesgo] = "Alto")', "0", ""),
    ],
    "pbi_regional": [
        ("TFR 2025 por si-do", "CALCULATE(AVERAGE(pbi_regional[TFR]), pbi_regional[anio] = 2025)", "0.00", ""),
    ],
    "pbi_internacional": [
        ("Fecundidad (país)", 'CALCULATE(AVERAGE(pbi_internacional[valor]), pbi_internacional[indicador] = "Fecundidad (TFR)")', "0.00", ""),
        ("65+ (país)", 'CALCULATE(AVERAGE(pbi_internacional[valor]), pbi_internacional[indicador] = "Población 65+ (%)")', "0.0", ""),
        ("Dependencia (país)", 'CALCULATE(AVERAGE(pbi_internacional[valor]), pbi_internacional[indicador] = "Dependencia de vejez")', "0.0", ""),
    ],
    "pbi_calidad": [
        ("Registros válidos (%)", "DIVIDE(SUM(pbi_calidad[registros_validos]), SUM(pbi_calidad[registros_evaluados])) * 100", "0.00", ""),
        ("Rechazo (%)", "DIVIDE(SUM(pbi_calidad[registros_rechazados]), SUM(pbi_calidad[registros_evaluados])) * 100", "0.00", ""),
        ("Registros evaluados", "SUM(pbi_calidad[registros_evaluados])", "#,0", ""),
    ],
    "pbi_conciliacion": [
        ("Pares dentro de ±3 %", "DIVIDE(SUMX(pbi_conciliacion, pbi_conciliacion[pares] * pbi_conciliacion[pct_dentro]), "
                                 "SUM(pbi_conciliacion[pares]))", '0.0" %"', ""),
    ],
    "pbi_okr": [("Resultados clave logrados", 'CALCULATE(COUNTROWS(pbi_okr), pbi_okr[estado] = "✅ Logrado") & " de " & COUNTROWS(pbi_okr)', "", "")],
}
RELACIONES = [("pbi_nacional", "anio", "pbi_anios", "anio"), ("pbi_escenarios", "anio", "pbi_anios", "anio"),
              ("pbi_flp", "anio", "pbi_anios", "anio"), ("pbi_internacional", "anio", "pbi_anios", "anio"),
              ("pbi_participacion", "anio", "pbi_anios", "anio"), ("pbi_regional", "anio", "pbi_anios", "anio"),
              ("pbi_riesgo", "cod_territorio", "pbi_territorio", "cod_territorio"),
              ("pbi_regional", "cod_territorio", "pbi_territorio", "cod_territorio")]
ORDEN_POR = {("pbi_piramide", "edad"): "orden", ("pbi_participacion", "edad"): "orden",
             ("pbi_escenarios", "escenario"): "orden_escenario", ("pbi_escenario_sel", "escenario"): "orden",
             ("pbi_territorio", "si_do"): "orden"}
DESCRIPCIONES = {
    "pbi_nacional": "Una fila por año (2000-2072), Corea del Sur. Vitales y laborales observados; población estimada hasta "
                    "2022 y desde la proyección KOSTAT medio después (columna tipo_dato_poblacion).",
    "pbi_escenarios": "Proyección oficial KOSTAT nacional en sus 8 escenarios (fecundidad, migración y envejecimiento).",
    "pbi_flp": "Escenario propio de fuerza laboral potencial (supuestos A/B/C/D) sobre cada escenario de KOSTAT. No es pronóstico.",
    "pbi_riesgo": "Índice de riesgo demográfico por si-do (inferencia propia, 4 componentes con igual peso).",
}


def _guid():
    return str(uuid.uuid4())


def _tipo(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_integer_dtype(s):
        return "int64"
    if pd.api.types.is_float_dtype(s):
        return "double"
    return "string"


def _q(nombre: str) -> str:
    return f"'{nombre}'" if not nombre.replace("_", "").isalnum() else nombre


def escribir_modelo(t: dict[str, pd.DataFrame], destino: Path, ruta_gold: str) -> None:
    d = destino / f"{NOMBRE}.SemanticModel"
    if d.exists():
        shutil.rmtree(d)
    (d / "definition" / "tables").mkdir(parents=True)
    (d / "definition.pbism").write_text(json.dumps({"version": "4.1", "settings": {}}, indent=2), encoding="utf-8")
    (d / "definition" / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n\n", encoding="utf-8")
    refs = "\n".join(f"ref table {_q(n)}" for n in t)
    orden = json.dumps(["RutaGold"] + list(t), ensure_ascii=False)
    (d / "definition" / "model.tmdl").write_text(
        "model Model\n\tculture: es-ES\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: es-CO\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {orden}\n\nannotation __PBI_TimeIntelligenceEnabled = 0\n\n{refs}\n\n", encoding="utf-8")
    (d / "definition" / "expressions.tmdl").write_text(
        "/// Carpeta de la capa gold del repositorio (termina en \\). Cambiarla en Transformar datos > Parámetros.\n"
        f'expression RutaGold = "{ruta_gold}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_guid()}\n\n\tannotation PBI_ResultType = Text\n\n", encoding="utf-8")
    rel = [f"relationship {_guid()}\n\tfromColumn: {a}.{ca}\n\ttoColumn: {b}.{cb}\n" for a, ca, b, cb in RELACIONES]
    (d / "definition" / "relationships.tmdl").write_text("\n".join(rel) + "\n", encoding="utf-8")
    for n, df in t.items():
        lin = [f"/// {DESCRIPCIONES[n]}"] if n in DESCRIPCIONES else []
        lin += [f"table {_q(n)}", f"\tlineageTag: {_guid()}", ""]
        for nombre, expr, fmt, desc in MEDIDAS.get(n, []):
            if desc:
                lin.append(f"\t/// {desc}")
            lin.append(f"\tmeasure '{nombre}' = {expr}")
            if fmt:
                lin.append(f"\t\tformatString: {fmt}")
            lin += [f"\t\tlineageTag: {_guid()}", ""]
        for col in df.columns:
            tipo = _tipo(df[col])
            lin += [f"\tcolumn {_q(col)}", f"\t\tdataType: {tipo}"]
            if tipo == "double":
                lin.append("\t\tformatString: 0.00")
            elif tipo == "int64":
                lin.append("\t\tformatString: 0")
            lin += [f"\t\tlineageTag: {_guid()}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {col}"]
            if (n, col) in ORDEN_POR:
                lin.append(f"\t\tsortByColumn: {ORDEN_POR[(n, col)]}")
            if n == "pbi_territorio" and col == "nombre_ingles":
                lin.append("\t\tdataCategory: StateOrProvince")
            lin += ["", "\t\tannotation SummarizationSetBy = User", ""]
        lin += [f"\tpartition {_q(n)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
                f'\t\t\t\t\tFuente = Parquet.Document(File.Contents(RutaGold & "powerbi\\{n}.parquet"))',
                "\t\t\t\tin", "\t\t\t\t\tFuente", "", "\tannotation PBI_ResultType = Table", ""]
        (d / "definition" / "tables" / f"{n}.tmdl").write_text("\n".join(lin), encoding="utf-8")


def construir() -> Path:
    servicio = ruta("gold") / "powerbi"
    tablas = {f.stem: pd.read_parquet(f) for f in sorted(servicio.glob("pbi_*.parquet"))}
    if not tablas:
        raise LookupError("No está la capa de servicio. Correr antes: python main.py --capa gold")
    orden = list(MEDIDAS) + [n for n in tablas if n not in MEDIDAS]
    tablas = {n: tablas[n] for n in orden if n in tablas}
    escribir_modelo(tablas, DESTINO, str(ruta("gold")) + "\\")
    pbip = DESTINO / f"{NOMBRE}.pbip"
    pbip.write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NOMBRE}.Report"}}],
                                "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    return pbip


if __name__ == "__main__":
    print(construir())
