"""Diccionario de datos generado desde PostgreSQL: tablas, columnas e indicadores de bronze, silver, gold y ctl.

Las columnas y tipos se leen de information_schema (así el diccionario no se desactualiza respecto al esquema real);
las descripciones vienen de config/mappings/tablas.csv y columnas.csv, y los indicadores de silver.dim_indicador.
Escribe docs/diccionario_datos.md y docs/diccionario_datos.xlsx.

Uso:
    python -m src.quality.diccionario
"""
import logging

import pandas as pd

from src.utils.config import RAIZ, ruta
from src.utils.db import conectar

log = logging.getLogger("diccionario")
ESQUEMAS = ("bronze", "silver", "gold", "ctl")
CAPAS = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold", "ctl": "Control"}


def _leer(conn, consulta: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(consulta)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def construir(conn) -> dict[str, pd.DataFrame]:
    esquemas = ", ".join(f"'{e}'" for e in ESQUEMAS)
    cols = _leer(conn, f"""
        SELECT c.table_schema || '.' || c.table_name AS tabla, t.table_type, c.ordinal_position AS orden,
               c.column_name AS columna, c.data_type AS tipo, c.is_nullable = 'YES' AS admite_nulo
        FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema IN ({esquemas})""")
    pk = _leer(conn, f"""
        SELECT k.table_schema || '.' || k.table_name AS tabla, k.column_name AS columna
        FROM information_schema.table_constraints c
        JOIN information_schema.key_column_usage k USING (constraint_schema, constraint_name)
        WHERE c.constraint_type = 'PRIMARY KEY' AND c.table_schema IN ({esquemas})""").assign(clave_primaria=True)
    filas = _leer(conn, "SELECT relnamespace::regnamespace::text || '.' || relname AS tabla, reltuples::bigint AS filas_aprox "
                        "FROM pg_class WHERE relkind = 'r'")

    desc_tablas = pd.read_csv(ruta("mappings") / "tablas.csv")
    desc_cols = pd.read_csv(ruta("mappings") / "columnas.csv", keep_default_na=False)
    especificas = desc_cols[desc_cols["tabla"] != ""].set_index(["tabla", "columna"])["descripcion"]
    genericas = desc_cols[desc_cols["tabla"] == ""].set_index("columna")["descripcion"]

    cols = cols.merge(pk, on=["tabla", "columna"], how="left").fillna({"clave_primaria": False})
    cols["descripcion"] = [especificas.get((t, c), genericas.get(c, "")) for t, c in zip(cols["tabla"], cols["columna"])]
    cols = cols.sort_values(["tabla", "orden"])

    tablas = (cols.groupby(["tabla", "table_type"], as_index=False).agg(columnas=("columna", "size"))
              .merge(desc_tablas, on="tabla", how="left").merge(filas, on="tabla", how="left"))
    tablas["esquema"] = tablas["tabla"].str.split(".").str[0]
    tablas["objeto"] = tablas["table_type"].map({"BASE TABLE": "tabla", "VIEW": "vista"})
    tablas["clave_primaria"] = tablas["tabla"].map(cols[cols["clave_primaria"]].groupby("tabla")["columna"].agg(", ".join))
    tablas["orden_esquema"] = tablas["esquema"].map({e: i for i, e in enumerate(ESQUEMAS)})
    tablas = tablas.sort_values(["orden_esquema", "objeto", "tabla"])[
        ["esquema", "tabla", "objeto", "descripcion", "grano", "clave_primaria", "columnas", "filas_aprox"]]

    indicadores = _leer(conn, "SELECT * FROM silver.dim_indicador ORDER BY es_derivado, cod_indicador")

    sin_desc = cols.loc[cols["descripcion"] == "", ["tabla", "columna"]]
    if not sin_desc.empty:
        log.warning("Columnas sin descripción en columnas.csv: %s", ", ".join(sin_desc["tabla"] + "." + sin_desc["columna"]))
    faltan = tablas.loc[tablas["descripcion"].isna(), "tabla"]
    if not faltan.empty:
        log.warning("Tablas sin descripción en tablas.csv: %s", ", ".join(faltan))
    return {"tablas": tablas, "columnas": cols[["tabla", "columna", "tipo", "clave_primaria", "admite_nulo", "descripcion"]],
            "indicadores": indicadores}


def _md_tabla(df: pd.DataFrame) -> str:
    texto = df.astype(object).where(df.notna(), "").astype(str).apply(lambda s: s.str.replace("|", "\\|", regex=False))
    lineas = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lineas += ["| " + " | ".join(r) + " |" for r in texto.itertuples(index=False)]
    return "\n".join(lineas)


def escribir(d: dict[str, pd.DataFrame], destino=RAIZ / "docs") -> None:
    destino.mkdir(parents=True, exist_ok=True)
    cols, tablas, ind = d["columnas"], d["tablas"], d["indicadores"]
    documentadas = (cols["descripcion"] != "").mean() * 100
    partes = [
        "# Diccionario de datos",
        "",
        "Generado con `python -m src.quality.diccionario` desde el esquema real de PostgreSQL (`information_schema`). "
        "Las descripciones están en `config/mappings/tablas.csv` y `columnas.csv`; los indicadores, en "
        "`silver.dim_indicador` (`config/mappings/indicadores.csv`). No editar a mano.",
        "",
        f"- Tablas y vistas: {len(tablas)} ({(tablas['objeto'] == 'tabla').sum()} tablas, {(tablas['objeto'] == 'vista').sum()} vistas).",
        f"- Columnas: {len(cols)}, documentadas el {documentadas:.0f} %.",
        f"- Indicadores: {len(ind)} ({int(ind['es_derivado'].sum())} calculados en el pipeline).",
        "",
        "## Indicadores",
        "",
        _md_tabla(ind.assign(es_derivado=ind["es_derivado"].map({True: "sí", False: "no"}))[["cod_indicador", "nombre", "definicion", "unidad", "frecuencia_original", "fuente_maestra",
                       "fuente_contraste", "es_derivado", "rango_min", "rango_max"]]),
        "",
        "## Tablas y vistas",
        "",
        _md_tabla(tablas.drop(columns="filas_aprox")),
    ]
    for esquema in ESQUEMAS:
        partes += ["", f"## Columnas: {CAPAS[esquema]} (`{esquema}`)"]
        for t in tablas.loc[tablas["esquema"] == esquema, "tabla"]:
            c = cols[cols["tabla"] == t].assign(clave_primaria=lambda x: x["clave_primaria"].map({True: "PK", False: ""}),
                                                admite_nulo=lambda x: x["admite_nulo"].map({True: "sí", False: "no"}))
            partes += ["", f"### {t}", "", _md_tabla(c.drop(columns="tabla"))]
    (destino / "diccionario_datos.md").write_text("\n".join(partes) + "\n", encoding="utf-8")

    with pd.ExcelWriter(destino / "diccionario_datos.xlsx", engine="openpyxl") as xls:
        for hoja, df in (("indicadores", ind), ("tablas", tablas), ("columnas", cols)):
            df.to_excel(xls, sheet_name=hoja, index=False)
            ws = xls.sheets[hoja]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                ancho = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 70)
    log.info("Diccionario: %d tablas/vistas, %d columnas (%.0f %% documentadas), %d indicadores -> %s",
             len(tablas), len(cols), documentadas, len(ind), destino)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with conectar() as conn:
        escribir(construir(conn))
