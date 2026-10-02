"""Métricas de calidad para el perfilamiento de datasets (KPIs de la sección 6 del documento)."""
import pandas as pd


def completitud(df: pd.DataFrame, por: list[str], anios: range, col_valor: str = "valor") -> pd.DataFrame:
    # Celdas esperadas = grupos x años; una celda cuenta si tiene valor no nulo.
    con_dato = df[df["anio"].isin(anios) & df[col_valor].notna()].groupby(por)["anio"].nunique()
    grupos = df[por].drop_duplicates().set_index(por).index
    out = pd.DataFrame({"anios_con_dato": con_dato.reindex(grupos, fill_value=0)})
    out["anios_esperados"] = len(anios)
    out["completitud_pct"] = (out["anios_con_dato"] / len(anios) * 100).round(1)
    return out.sort_values("completitud_pct")


def duplicados(df: pd.DataFrame, clave: list[str]) -> int:
    return int(df.duplicated(subset=clave).sum())


def fuera_de_rango(df: pd.DataFrame, rmin=None, rmax=None, col_valor: str = "valor") -> pd.DataFrame:
    v = df[col_valor]
    malo = pd.Series(False, index=df.index)
    if rmin is not None:
        malo |= v < rmin
    if rmax is not None:
        malo |= v > rmax
    return df[malo]


def dif_pct(maestra: pd.Series, contraste: pd.Series) -> pd.Series:
    return (contraste - maestra) / maestra.abs() * 100


def resumen_conciliacion(dif: pd.Series, tolerancia_pct: float = 3.0) -> dict:
    d = dif.dropna()
    return {"pares": len(d), "dentro_tolerancia": int((d.abs() <= tolerancia_pct).sum()),
            "pct_dentro": round((d.abs() <= tolerancia_pct).mean() * 100, 1) if len(d) else None,
            "dif_max_abs_pct": round(d.abs().max(), 2) if len(d) else None}
