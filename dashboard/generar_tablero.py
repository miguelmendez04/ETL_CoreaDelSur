"""Versión web del tablero de Power BI (un solo archivo, funciona sin conexión). Diseño del equipo (Angie Rodríguez).

Lee la misma capa de servicio que Power BI (data/gold/powerbi/pbi_*.parquet, generada por la capa gold) y replica sus
8 páginas: portada, resumen, natalidad, envejecimiento, fuerza laboral, regiones, Corea vs OCDE y calidad. Gráficos
interactivos con Plotly (información al pasar el cursor, leyendas que encienden/apagan series, selectores de año y de
escenario). Las imágenes son las del reporte de Power BI (powerbi/Tablero_ETL_Corea_Grupo6.Report).

Uso:
    python dashboard/generar_tablero.py      ->  dashboard/Tablero_ETL_Corea_Grupo6.html
"""
import base64
import html
import io
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from PIL import Image
from plotly.offline import get_plotlyjs

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from src.utils.config import ruta  # noqa: E402

SERV = ruta("gold") / "powerbi"
GRAF = RAIZ / "powerbi" / "Tablero_ETL_Corea_Grupo6.Report" / "StaticResources" / "RegisteredResources"
SALIDA = RAIZ / "dashboard" / "Tablero_ETL_Corea_Grupo6.html"

# misma paleta del tablero de Power BI (azul marino de estructura; rojo y azul de la bandera de Corea como acentos)
MARINO, ROJO, AZUL, AMBAR, VERDE, PURPURA, GRIS = "#0F2747", "#CD2E3A", "#0047A0", "#D98E04", "#2F8F7F", "#8E6BB0", "#8C96A5"
TINTA, TINTA2, REJILLA = "#1E2430", "#5F6B7A", "#E9EDF3"
MENU = [("resumen", "Resumen"), ("natalidad", "Natalidad"), ("envejecimiento", "Envejecimiento"),
        ("fuerza_laboral", "Fuerza laboral"), ("regiones", "Regiones"), ("contexto_ocde", "Corea vs OCDE"),
        ("calidad", "Calidad y OKR")]


def s(n):
    return pd.read_parquet(SERV / f"{n}.parquet")


def es(v, d=1):
    """Número con formato español (coma decimal, punto de miles)."""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def img64(nombre, ancho=900, recorte=None, png=False):
    im = Image.open(GRAF / nombre)
    if recorte:
        im = im.crop(recorte(im))
    if im.width > ancho:
        im = im.resize((ancho, int(im.height * ancho / im.width)), Image.LANCZOS)
    b = io.BytesIO()
    if png:
        im.convert("RGBA").save(b, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    im.convert("RGB").save(b, "JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


# =============================================================================== figuras
def base_layout(fig, titulo_y=None, leyenda=True, hover="x unified"):
    fig.update_layout(
        separators=",.", font=dict(family="Segoe UI, system-ui, sans-serif", size=12, color=TINTA2),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=48, r=16, t=34 if leyenda else 12, b=36),
        hovermode=hover, hoverlabel=dict(bgcolor="white", bordercolor="#E3E8F0", font=dict(color=TINTA, size=12)),
        showlegend=leyenda, legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(color=TINTA, size=11), bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(showgrid=False, linecolor="#C9D1DC", tickfont=dict(color=TINTA2), zeroline=False)
    fig.update_yaxes(gridcolor=REJILLA, zeroline=False, tickfont=dict(color=TINTA2), title_text=titulo_y or "",
                     title_font=dict(size=11))
    return fig


def lin(x, y, nombre, color, ancho=2.5, guion=None, fmt=",.1f"):
    return go.Scatter(x=x, y=y, name=nombre, mode="lines", line=dict(color=color, width=ancho, dash=guion),
                      hovertemplate=f"%{{y:{fmt}}}<extra>{nombre}</extra>", connectgaps=False)


def figuras():
    n = s("pbi_nacional").sort_values("anio")
    terr = s("pbi_territorio")
    F = {}
    obs = n[n.anio <= 2025]
    # --- natalidad
    f = go.Figure(go.Bar(x=obs.anio, y=obs.NACIMIENTOS / 1000, marker=dict(color=AZUL, cornerradius=3), name="Nacimientos",
                         hovertemplate="%{x}: %{y:,.0f} mil nacimientos<extra></extra>"))
    F["nac"] = base_layout(f, "miles", leyenda=False, hover="closest")
    f = go.Figure([lin(obs.anio, obs.TFR, "Fecundidad (TFR)", ROJO, 3, fmt=".2f"),
                   lin(obs.anio, [2.1] * len(obs), "Nivel de reemplazo (2,1)", GRIS, 1.5, "dash", ".1f")])
    F["tfr"] = base_layout(f, "hijos por mujer")
    r = s("pbi_regional").merge(terr[["cod_territorio", "si_do"]])
    r25 = r[r.anio == 2025].dropna(subset=["TFR"]).sort_values("TFR", ascending=False)
    f = go.Figure(go.Bar(y=r25.si_do, x=r25.TFR, orientation="h", marker=dict(color=ROJO, cornerradius=3),
                         text=[es(v, 2) for v in r25.TFR], textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x:.2f} hijos por mujer<extra></extra>"))
    F["tfr_sido"] = base_layout(f, leyenda=False, hover="closest")
    F["tfr_sido"].update_layout(margin=dict(l=120, r=40, t=10, b=30))
    f = go.Figure([lin(obs.anio, obs.NACIMIENTOS / 1000, "Nacimientos (miles)", AZUL, fmt=",.0f"),
                   lin(obs.anio, obs.DEFUNCIONES / 1000, "Defunciones (miles)", MARINO, fmt=",.0f")])
    F["nac_def"] = base_layout(f, "miles")
    # --- envejecimiento
    pir = s("pbi_piramide")
    anios_pir = s("pbi_anio_sel").anio_piramide.tolist()
    F["piramide"] = {}
    for a in anios_pir:
        d = pir[pir.anio == a].sort_values("orden")
        h, m = d[d.sexo == "Hombres"], d[d.sexo == "Mujeres"]
        f = go.Figure([go.Bar(y=h.edad, x=-h.pct, orientation="h", name="Hombres", marker=dict(color=AZUL),
                              customdata=h.pct, hovertemplate="Hombres %{y}: %{customdata:.1f} %<extra></extra>"),
                       go.Bar(y=m.edad, x=m.pct, orientation="h", name="Mujeres", marker=dict(color=ROJO),
                              hovertemplate="Mujeres %{y}: %{x:.1f} %<extra></extra>")])
        f = base_layout(f, hover="closest")
        lim = max(pir.pct.max(), 1) * 1.05
        f.update_layout(barmode="overlay", bargap=0.12, margin=dict(l=56, r=16, t=34, b=36))
        f.update_xaxes(range=[-lim, lim], tickvals=[-4, -2, 0, 2, 4], ticktext=["4 %", "2 %", "0", "2 %", "4 %"])
        F["piramide"][str(a)] = f
    pob = n[n.PROP_65MAS.notna()]
    f = go.Figure([lin(pob.anio, pob.PROP_0_14, "0-14 años", AMBAR), lin(pob.anio, pob.PROP_15_64, "15-64 años", AZUL),
                   lin(pob.anio, pob.PROP_65MAS, "65 años y más", ROJO)])
    f.add_vline(x=2022.5, line=dict(color=GRIS, width=1, dash="dot"))
    f.add_annotation(x=2023, y=1, yref="paper", text="proyección →", showarrow=False, xanchor="left", font=dict(size=10, color=TINTA2))
    F["grupos"] = base_layout(f, "% de la población")
    est = n[n.tipo_dato_poblacion == "estimado"]
    pro = n[(n.tipo_dato_poblacion != "estimado") | (n.anio == est.anio.max())]
    f = go.Figure([lin(est.anio, est.DEP_VEJEZ, "Estimada", ROJO, 3), lin(pro.anio, pro.DEP_VEJEZ, "Proyección KOSTAT", ROJO, 3, "dash")])
    F["dep"] = base_layout(f, "mayores por cada 100 de 15-64")
    ev = n[n.ESPERANZA_VIDA.notna()]
    F["ev"] = base_layout(go.Figure(lin(ev.anio, ev.ESPERANZA_VIDA, "Esperanza de vida", VERDE, 3)), "años", leyenda=False)
    # --- fuerza laboral
    e = s("pbi_escenarios")
    e = e[e.indicador == "Población 15-64 (millones)"].sort_values(["orden_escenario", "anio"])
    colores_esc = [MARINO, ROJO, AZUL, AMBAR, "#C08A2E", VERDE, PURPURA, GRIS]
    f = go.Figure([lin(d.anio, d.valor, nom, colores_esc[i % len(colores_esc)], 3.5 if i == 0 else 2)
                   for i, (nom, d) in enumerate(e.groupby("escenario", sort=False))])
    F["esc"] = base_layout(f, "millones")
    flp = s("pbi_flp").sort_values("anio")
    escs = s("pbi_escenario_sel").sort_values("orden").escenario.tolist()
    F["flp"] = {}
    for esc in escs:
        d = flp[flp.escenario == esc]
        f = go.Figure([lin(g_.anio, g_.flp / 1e6, sup, c, 2.5, fmt=",.2f")
                       for (sup, g_), c in zip(d.groupby("supuesto", sort=True), [ROJO, AZUL, AMBAR, PURPURA])])
        F["flp"][esc] = base_layout(f, "millones")
    irl_e = n[(n.tipo_dato_poblacion == "estimado") & n.IND_REEMPLAZO_LABORAL.notna()]
    irl_p = n[((n.tipo_dato_poblacion != "estimado") | (n.anio == irl_e.anio.max())) & n.IND_REEMPLAZO_LABORAL.notna()]
    f = go.Figure([lin(irl_e.anio, irl_e.IND_REEMPLAZO_LABORAL, "Estimado", AZUL, 3, fmt=".0f"),
                   lin(irl_p.anio, irl_p.IND_REEMPLAZO_LABORAL, "Proyección KOSTAT", AZUL, 3, "dash", ".0f"),
                   lin([irl_e.anio.min(), 2072], [100, 100], "Referencia 100", GRIS, 1.5, "dot", ".0f")])
    F["reemplazo"] = base_layout(f, "jóvenes 15-24 por 100 de 55-64")
    p = s("pbi_participacion")
    p = p[p.anio == 2025].sort_values("orden")
    f = go.Figure([go.Bar(x=d.edad, y=d.tasa, name=sx, marker=dict(color=c, cornerradius=3), text=[es(v) for v in d.tasa],
                          textposition="outside", cliponaxis=False, hovertemplate=f"{sx} %{{x}}: %{{y:.1f}} %<extra></extra>")
                   for (sx, d), c in zip(p.groupby("sexo", sort=True), [AZUL, ROJO])])
    F["part"] = base_layout(f, "% de participación", hover="closest")
    F["part"].update_layout(bargap=0.25, bargroupgap=0.08)
    # --- regiones
    rg = s("pbi_riesgo").merge(terr[["cod_territorio", "si_do"]]).sort_values("indice_riesgo")
    col_nivel = {"Alto": ROJO, "Medio": AMBAR, "Bajo": AZUL}
    f = go.Figure([go.Bar(y=d.si_do, x=d.indice_riesgo, orientation="h", name=f"Riesgo {niv.lower()}",
                          marker=dict(color=col_nivel[niv], cornerradius=3), text=[es(v, 1) for v in d.indice_riesgo],
                          textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}: índice %{x:.1f}<extra>" + f"Riesgo {niv.lower()}</extra>")
                   for niv, d in rg.groupby("nivel_riesgo", sort=False)])
    F["indice"] = base_layout(f, hover="closest")
    F["indice"].update_layout(margin=dict(l=130, r=40, t=34, b=30), barmode="relative", legend=dict(traceorder="reversed"))
    F["indice"].update_xaxes(range=[0, rg.indice_riesgo.max() * 1.12])
    F["indice"].update_yaxes(categoryorder="array", categoryarray=rg.si_do.tolist())
    # --- OCDE
    it = s("pbi_internacional").sort_values("anio")
    col_pais = {"Corea del Sur": ROJO, "Promedio OCDE": MARINO, "Japón": AZUL, "Italia": AMBAR, "Estados Unidos": VERDE,
                "Alemania": PURPURA, "España": "#A7B0BE", "Francia": "#C9B8D9"}
    for clave, ind, unidad, fmt in (("o_tfr", "TFR", "hijos por mujer", ".2f"), ("o_65", "PROP_65MAS", "% de la población", ".1f"),
                                    ("o_dep", "DEP_VEJEZ", "por cada 100 de 15-64", ".1f")):
        d = it[it.cod_indicador == ind]
        f = go.Figure([lin(d[d.pais == pais].anio, d[d.pais == pais].valor, pais, c, 5 if pais == "Corea del Sur" else 1.8,
                           "dash" if pais == "Promedio OCDE" else None, fmt) for pais, c in col_pais.items()])
        F[clave] = base_layout(f, unidad)
    pib = n[n.PIB_HORA.notna()]
    F["pib"] = base_layout(go.Figure(lin(pib.anio, pib.PIB_HORA, "PIB por hora", AZUL, 3)), "USD PPA", leyenda=False)
    return F


# =============================================================================== HTML
def tabla_html(df, columnas, clase=""):
    cab = "".join(f"<th>{html.escape(c)}</th>" for c in columnas.values())
    filas = []
    for _, r in df.iterrows():
        celdas = []
        for k in columnas:
            v = r[k]
            if k == "semaforo":
                v = f'<span class="sem sem-{html.escape(str(v)).lower()}">{html.escape(str(v))}</span>'
            elif k == "estado":
                v = f'<span class="ok">✔ {html.escape(str(v).replace("✅", "").strip())}</span>'
            elif isinstance(v, float):
                v = es(v, 2)
            else:
                v = html.escape(str(v))
            celdas.append(f"<td>{v}</td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    return f'<div class="tabla {clase}"><table><thead><tr>{cab}</tr></thead><tbody>{"".join(filas)}</tbody></table></div>'


def tarjeta(valor, etiqueta, nota, color):
    return (f'<div class="kpi" style="--acento:{color}"><div class="kpi-valor">{html.escape(valor)}</div>'
            f'<div class="kpi-etq">{html.escape(etiqueta)}</div><div class="kpi-nota">{html.escape(nota)}</div></div>')


def panel(titulo, cuerpo, sub="", clase=""):
    s_ = f'<p class="sub">{html.escape(sub)}</p>' if sub else ""
    return f'<div class="panel {clase}"><h3>{html.escape(titulo)}</h3>{s_}{cuerpo}</div>'


def graf(id_, alto=300):
    return f'<div class="graf" id="g_{id_}" style="height:{alto}px"></div>'


def nota(titulo, lineas, color=AZUL):
    ps = "".join(f"<p>{html.escape(l)}</p>" for l in lineas)
    return f'<div class="nota" style="--acento:{color}"><h4>{html.escape(titulo)}</h4>{ps}</div>'


def construir():
    F = figuras()
    k = s("pbi_kpi").set_index("codigo")
    okr, cal, con = s("pbi_okr"), s("pbi_calidad"), s("pbi_conciliacion")
    terr = s("pbi_territorio")
    rg = s("pbi_riesgo").merge(terr[["cod_territorio", "si_do"]]).sort_values("ranking_riesgo")
    img = {"fondo": img64("fondo3.jpg", 1600), "madre": img64("madre_bebe.jpg", 700), "familia": img64("familia.jpg", 700),
           "trab": img64("trabajadores.jpg", 900), "seul": img64("trabajadores_seul.jpg", 500),
           "mapa": img64("mapa_corea.png", 700, png=True), "bandera": img64("bandera_coreadelsur.png", 160, png=True),
           "logo": img64("logo_uao2_blanco.png", 400, png=True)}
    n_esc = s("pbi_escenario_sel").shape[0]
    top3 = f"{rg.si_do.iloc[0]}, {rg.si_do.iloc[1]} y {rg.si_do.iloc[2]}"

    def kv(c):
        r = k.loc[c]
        u = {"%": " %", "puntos porcentuales": " pp"}.get(r.unidad, "")
        return f"{r.valor_texto}{u}".replace("-", "−")

    validos = cal.registros_validos.sum() / cal.registros_evaluados.sum() * 100
    rechazo = cal.registros_rechazados.sum() / cal.registros_evaluados.sum() * 100
    pares = (con.pares * con.pct_dentro).sum() / con.pares.sum()
    logrados = int(okr.estado.str.contains("Logrado").sum())

    secciones = {}
    secciones["resumen"] = (f"Corea del Sur en {len(k)} indicadores", "Resumen ejecutivo · último valor, referencia y semáforo de cada KPI",
        '<div class="kpis">' + "".join(tarjeta(kv(c), et, nt, col) for c, et, nt, col in [
            ("KPI-01", "Fecundidad 2025", "reemplazo: 2,1", ROJO), ("KPI-02", "Nacimientos vs 2000", "observado · KOSIS", AZUL),
            ("KPI-05", "% 65+ en 2025", "ONU: ≥ 20 % superenvejecida", MARINO), ("KPI-07", "Pob. 15-64 a 2050", "proyección oficial", ROJO),
            ("KPI-08", "Reemplazo laboral", "jóvenes por 100 a retiro", AMBAR), ("KPI-11", "Fuerza laboral a 2050", "escenario propio A", VERDE)])
        + '</div><div class="fila f-2-1">'
        + panel(f"{len(k)} KPIs del problema · una fórmula cada uno",
                tabla_html(s("pbi_kpi"), {"codigo": "KPI", "indicador": "Indicador", "ultimo_valor": "Último valor",
                                          "referencia": "Referencia", "semaforo": "Semáforo"}))
        + f'<div class="col"><div class="foto" style="background-image:url({img["madre"]})"></div>'
        + nota("¿Qué nos dicen los datos?", ["La fecundidad está en 38 % del nivel de reemplazo y los nacimientos cayeron 60 % desde 2000.",
                                             f"La población en edad de trabajar perderá cerca de un tercio a 2050 en los {n_esc} escenarios oficiales.",
                                             "Línea continua = dato observado · discontinua = proyección oficial."]) + "</div></div>")
    secciones["natalidad"] = ("Natalidad y fecundidad", "Datos observados · KOSIS, estadísticas vitales 2000-2025 y TFR por si-do",
        '<div class="fila f-1-1">' + panel("Nacimientos por año (miles)", graf("nac")) +
        panel("Hijos por mujer frente al nivel de reemplazo (2,1)", graf("tfr")) + '</div><div class="fila f-nat">' +
        panel("Fecundidad 2025 por si-do", graf("tfr_sido", 330)) +
        panel("Nacimientos vs defunciones (miles)", graf("nac_def", 300), "desde 2020 mueren más personas de las que nacen") +
        f'<div class="foto alta" style="background-image:url({img["familia"]})"></div></div>')
    sel_pir = "".join(f'<option value="{a}"{" selected" if a == "2025" else ""}>{a}</option>' for a in F["piramide"])
    secciones["envejecimiento"] = ("Envejecimiento de la población", "Estimación oficial hasta 2022 · proyección KOSTAT (escenario medio) desde 2023",
        '<div class="fila f-1-2">' + panel("Pirámide de población (% del total)",
              f'<label class="selector">Año <select id="sel_pir">{sel_pir}</select></label>' + graf("piramide", 520)) +
        '<div class="col">' + panel("Grandes grupos de edad (% de la población)", graf("grupos", 250)) +
        '<div class="fila f-1-1">' + panel("Mayores por cada 100 personas en edad de trabajar", graf("dep", 220)) +
        panel("Esperanza de vida (años)", graf("ev", 220)) + "</div></div></div>")
    sel_esc = "".join(f'<option>{html.escape(e_)}</option>' for e_ in F["flp"])
    secciones["fuerza_laboral"] = ("Fuerza laboral futura",
        f"Escenarios oficiales KOSTAT ({n_esc}) y supuestos propios A/B/C/D de participación (no son pronósticos)",
        '<div class="fila f-1-1">' + panel("Población de 15-64 años por escenario oficial (millones)", graf("esc", 320)) +
        panel("Fuerza laboral potencial (millones) · escenario propio",
              f'<label class="selector">Escenario de población <select id="sel_flp">{sel_esc}</select></label>' + graf("flp", 280)) +
        '</div><div class="fila f-1-1">' + panel("Señal temprana: jóvenes 15-24 por cada 100 de 55-64", graf("reemplazo")) +
        panel("Participación laboral por edad y sexo, 2025 (%)", graf("part")) + "</div>")
    n_alto = int((rg.nivel_riesgo == "Alto").sum())
    secciones["regiones"] = ("¿Dónde es mayor el riesgo?",
        "Índice de riesgo demográfico 2025 → 2052 · inferencia propia con 4 componentes y ponderación igual",
        '<div class="fila f-1-1">' + panel("Índice de riesgo por si-do (mayor = más riesgo)", graf("indice", 560)) + '<div class="col">' +
        panel("Componentes del índice (2025)", tabla_html(rg, {"si_do": "Si-do", "nivel_riesgo": "Nivel", "tfr": "TFR",
              "prop_65mas": "% 65+", "dep_vejez": "Dependencia", "tasa_participacion": "Particip.",
              "var_pob_15_64_2052_pct": "Δ 15-64 a 2052 %"}, "compacta")) +
        f'<div class="fila f-1-1"><div class="foto mapa" style="background-image:url({img["mapa"]})"></div><div class="col">' +
        tarjeta(str(n_alto), "si-do en riesgo alto", "tercil superior del índice", ROJO) +
        nota("Lectura", [f"{top3}: alta proporción de 65+, baja fecundidad y mayor pérdida proyectada de población 15-64."], ROJO) +
        "</div></div></div></div>")
    secciones["contexto_ocde"] = ("Corea frente a la OCDE",
        "World Bank WDI para los países · Corea con KOSIS (fuente maestra) · OECD productividad · Corea en rojo",
        '<div class="fila f-1-1">' + panel("Tasa global de fecundidad", graf("o_tfr")) + panel("Población de 65 años y más (%)", graf("o_65")) +
        '</div><div class="fila f-ocde">' + panel("Dependencia de vejez", graf("o_dep")) +
        panel("PIB por hora trabajada, Corea (USD PPA)", graf("pib"), "asociación, no causalidad") +
        f'<div class="foto alta" style="background-image:url({img["seul"]})"></div></div>')
    secciones["calidad"] = ("Calidad del dato y OKR", "OKR orientados al problema (O1-O3) y objetivo habilitador de calidad (O4)",
        '<div class="kpis k4">' + tarjeta(f"{logrados} de {len(okr)}", "resultados clave (O1-O4)", "última ejecución", VERDE) +
        tarjeta(es(validos, 2) + " %", "registros válidos", "meta ≥ 98 %", AZUL) + tarjeta(es(rechazo, 2) + " %", "rechazo trazado", "meta ≤ 2 %", ROJO) +
        tarjeta(es(pares) + " %", "pares conciliados ±3 %", "maestra vs contraste", MARINO) + "</div>" +
        panel("O1 diagnóstico · O2 impacto laboral · O3 decisión · O4 calidad",
              tabla_html(okr.assign(valor=okr.valor.str.replace(r"(\d)\.(\d)", r"\1,\2", regex=True),
                                    meta=okr.meta.str.replace(r"(\d)\.(\d)", r"\1,\2", regex=True)),
                         {"kr": "KR", "kpi": "Resultado clave", "meta": "Meta", "valor": "Logrado", "estado": "Estado"})) +
        '<div class="fila f-1-1">' + panel("Reglas de calidad por dataset", tabla_html(cal.sort_values("tasa_validos_pct"),
              {"dataset": "Dataset", "tasa_validos_pct": "% válidos", "registros_rechazados": "Rechazados"}, "compacta alta")) +
        nota("Controles aplicados en cada corrida", [
            "Tipos · nulos esperados e inesperados · duplicados · rangos por indicador · años válidos · integridad referencial · "
            "Σ si-do = nacional · H + M = total · conciliación ±3 % con las fuentes de contraste.",
            "Nada se corrige en silencio: cada rechazo queda en ctl.rechazos con su motivo."]) + "</div>")

    iconos = {"resumen": "📊", "natalidad": "👶", "envejecimiento": "👴", "fuerza_laboral": "💼", "regiones": "🗺️",
              "contexto_ocde": "🌐", "calidad": "✔"}
    menu = "".join(f'<a href="#{c}" data-p="{c}">{html.escape(n_)}</a>' for c, n_ in MENU)
    botones = "".join(f'<a class="btn {"rojo" if i % 2 == 0 else "azul"}" href="#{c}">{html.escape(n_)}</a>'
                      for i, (c, n_) in enumerate(MENU))
    paginas = "".join(
        f'<section class="pagina" id="p_{c}"><header class="cab"><span class="ico">{iconos[c]}</span><div><h2>{html.escape(t)}</h2>'
        f'<p>{html.escape(sub)}</p></div><img class="bandera" src="{img["bandera"]}" alt="Bandera de Corea del Sur"></header>'
        f'<div class="contenido">{cuerpo}</div></section>' for c, (t, sub, cuerpo) in secciones.items())
    figs = {k_: (json.loads(v.to_json()) if hasattr(v, "to_json") else {kk: json.loads(vv.to_json()) for kk, vv in v.items()})
            for k_, v in F.items()}

    doc = PLANTILLA.format(css=CSS, plotly=get_plotlyjs(), figs=json.dumps(figs, ensure_ascii=False, separators=(",", ":")),
                           menu=menu, botones=botones, paginas=paginas, **img)
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(doc, encoding="utf-8")
    print(SALIDA, f"{SALIDA.stat().st_size / 1e6:.1f} MB")
    return SALIDA


CSS = """
:root{--marino:#0F2747;--marino2:#1C3A66;--rojo:#CD2E3A;--azul:#0047A0;--fondo:#F4F6FA;--borde:#E3E8F0;--tinta:#1E2430;
--tinta2:#5F6B7A;--azulclaro:#EAF0F9}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{font-family:"Segoe UI",system-ui,-apple-system,sans-serif;background:var(--fondo);color:var(--tinta);font-size:14px}
a{color:inherit;text-decoration:none}
/* portada */
#portada{position:fixed;inset:0;background-size:cover;background-position:center;display:flex;flex-direction:column;overflow:auto;z-index:5}
#portada::before{content:"";position:fixed;inset:0;background:rgba(90,6,18,.78);z-index:-1}
.p-top{display:flex;justify-content:space-between;align-items:center;padding:28px 40px}
.p-top img.logo{height:70px}.p-top img.bandera{height:52px;border-radius:4px}
.p-cuerpo{flex:1;display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:32px;padding:8px 40px 24px;align-items:center}
.p-panel{background:rgba(143,11,33,.88);border-radius:18px;padding:32px 34px;color:#fff}
.p-panel .eti{color:#F7C5CB;font-weight:600;font-size:12px;letter-spacing:.06em}
.p-panel h1{font-size:clamp(26px,3.2vw,40px);line-height:1.15;margin:10px 0 16px}
.p-panel .preg{color:#FFE4E7;font-size:16px;line-height:1.45;margin:0 0 18px}
.p-panel .equipo{font-weight:600;margin:0}.p-panel .maestria{color:#F7C5CB;font-size:13px;margin:4px 0 22px}
.entrar{display:inline-block;background:#fff;color:var(--rojo);font-weight:600;padding:12px 26px;border-radius:26px;font-size:16px}
.entrar:hover{background:#FBE3E5}
.p-fotos{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.p-fotos div{border:2px solid #fff;border-radius:14px;background-size:cover;background-position:center;aspect-ratio:1.1/1}
.p-fotos div.ancha{grid-column:span 2;aspect-ratio:2.3/1}
.p-nav{background:rgba(43,3,8,.75);padding:14px 40px 22px}.p-nav .eti{color:#F7C5CB;font-weight:600;font-size:12px;letter-spacing:.06em}
.p-nav .botones{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px}
.btn{color:#fff;font-weight:600;padding:11px 22px;border-radius:24px;min-width:140px;text-align:center}
.btn.rojo{background:var(--rojo)}.btn.azul{background:var(--azul)}.btn:hover{background:var(--marino)}
/* estructura */
.app{display:none;min-height:100%}.app.activa{display:flex}
nav.lateral{position:sticky;top:0;height:100vh;width:210px;flex:0 0 210px;background:var(--marino);padding:22px 14px;display:flex;flex-direction:column}
nav.lateral img{width:160px;margin:0 4px 18px}nav.lateral .eti{color:#8EA3C2;font-size:11px;font-weight:600;letter-spacing:.08em;margin:0 6px 10px}
nav.lateral a{display:block;color:#DCE4F0;font-weight:600;padding:10px 14px;border-radius:8px;margin-bottom:6px;position:relative}
nav.lateral a:hover{background:var(--marino2)}
nav.lateral a.actual{background:#fff;color:var(--marino)}
nav.lateral a.actual::before{content:"";position:absolute;left:-10px;top:8px;bottom:8px;width:4px;border-radius:2px;background:var(--rojo)}
nav.lateral a.volver{margin-top:auto;background:var(--marino2);color:#fff;text-align:center}nav.lateral a.volver:hover{background:var(--azul)}
main{flex:1;min-width:0}
.pagina{display:none}.pagina.activa{display:block}
.cab{display:flex;align-items:center;gap:14px;background:#fff;padding:14px 24px;border-top:5px solid;border-image:linear-gradient(90deg,var(--rojo) 50%,var(--azul) 50%) 1}
.cab .ico{width:46px;height:46px;border-radius:50%;background:var(--azulclaro);display:grid;place-items:center;font-size:22px;flex:none}
.cab h2{margin:0;color:var(--marino);font-size:24px}.cab p{margin:2px 0 0;color:var(--tinta2)}
.cab .bandera{margin-left:auto;height:38px}
.contenido{padding:16px 20px 28px;display:flex;flex-direction:column;gap:14px}
.fila{display:grid;gap:14px}.f-1-1{grid-template-columns:1fr 1fr}.f-2-1{grid-template-columns:2.6fr 1fr}.f-1-2{grid-template-columns:1fr 1.8fr}
.f-nat{grid-template-columns:1fr 1.1fr .5fr}.f-ocde{grid-template-columns:1fr .8fr .45fr}
.col{display:flex;flex-direction:column;gap:14px;min-width:0}
.panel{background:#fff;border:1px solid var(--borde);border-radius:10px;padding:12px 14px;box-shadow:0 2px 6px rgba(15,39,71,.05);min-width:0}
.panel h3{margin:0 0 4px;color:var(--marino);font-size:15px}.panel .sub{margin:0;color:var(--tinta2);font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}.kpis.k4{grid-template-columns:repeat(4,1fr)}
.kpi{background:#fff;border:1px solid var(--borde);border-radius:10px;padding:16px 12px 12px;text-align:center;position:relative;box-shadow:0 2px 6px rgba(15,39,71,.05)}
.kpi::before{content:"";position:absolute;left:14px;right:14px;top:0;height:5px;border-radius:0 0 3px 3px;background:var(--acento)}
.kpi-valor{font-size:28px;font-weight:600;color:var(--acento);font-variant-numeric:tabular-nums}
.kpi-etq{color:var(--tinta);font-size:13px;margin-top:2px}.kpi-nota{color:var(--tinta2);font-size:11px;margin-top:2px}
.tabla{overflow:auto;max-height:470px}.tabla.compacta{max-height:500px}.tabla.alta{max-height:300px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{background:var(--marino);color:#fff;text-align:left;padding:7px 8px;position:sticky;top:0;font-weight:600}
td{padding:6px 8px;border-bottom:1px solid var(--borde);font-variant-numeric:tabular-nums}tbody tr:nth-child(even){background:#F3F6FB}
.compacta td,.compacta th{padding:5px 6px;font-size:12px}
.sem{white-space:nowrap}.sem::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px;background:#B9C2CF}
.sem-crítico::before{background:var(--rojo)}.sem-alerta::before{background:#D98E04}.sem-normal::before{background:#2F8F7F}
.ok{color:#2F8F7F;font-weight:600;white-space:nowrap}
.foto{border-radius:12px;background-size:cover;background-position:center;min-height:200px;border:1px solid var(--borde);box-shadow:0 2px 6px rgba(15,39,71,.08)}
.foto.alta{min-height:330px}.foto.mapa{background-size:contain;background-repeat:no-repeat;background-color:#fff;min-height:220px}
.nota{background:var(--azulclaro);border-left:5px solid var(--acento);border-radius:10px;padding:12px 16px}
.nota h4{margin:0 0 6px;color:var(--acento);font-size:15px}.nota p{margin:0 0 6px;line-height:1.45}
.selector{display:inline-flex;gap:8px;align-items:center;color:var(--tinta2);font-size:12px;margin:4px 0}
.selector select{font:inherit;color:var(--tinta);border:1px solid var(--borde);border-radius:6px;padding:4px 8px;background:#fff}
@media (max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.f-nat,.f-ocde{grid-template-columns:1fr 1fr}.f-nat .foto,.f-ocde .foto{display:none}}
@media (max-width:820px){.app.activa{flex-direction:column}nav.lateral{position:static;height:auto;width:100%;flex:none;flex-direction:row;flex-wrap:wrap;gap:6px;padding:12px 16px}
nav.lateral img{width:110px;margin:0 8px 0 0}nav.lateral .eti{display:none}nav.lateral a{margin:0;padding:8px 10px}nav.lateral a.actual::before{display:none}nav.lateral a.volver{margin:0}
.f-1-1,.f-2-1,.f-1-2,.f-nat,.f-ocde,.p-cuerpo{grid-template-columns:1fr}.kpis,.kpis.k4{grid-template-columns:1fr 1fr}.contenido{padding:12px 16px}
.cab .bandera{display:none}.p-top,.p-cuerpo,.p-nav{padding-left:16px;padding-right:16px}}
"""

PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tablero ETL Corea · Grupo 6</title><style>{css}</style><script>{plotly}</script></head>
<body>
<div id="portada" style="background-image:url({fondo})">
 <div class="p-top"><img class="logo" src="{logo}" alt="Universidad Autónoma de Occidente"><img class="bandera" src="{bandera}" alt="Bandera de Corea del Sur"></div>
 <div class="p-cuerpo">
  <div class="p-panel"><div class="eti">PROYECTO ETL 2026 · GRUPO 6 · TABLERO DE ANÁLISIS</div>
   <h1>Natalidad, envejecimiento y fuerza laboral en Corea del Sur</h1>
   <p class="preg">¿Cómo impactará la disminución de la natalidad y el envejecimiento poblacional en la disponibilidad futura de la fuerza laboral?</p>
   <p class="equipo">Angie Rodríguez · Karin Parra · Maicol Narváez · Miguel Méndez</p>
   <p class="maestria">Maestría en Inteligencia Artificial y Ciencia de Datos · UAO</p>
   <a class="entrar" href="#resumen">Ingresar al tablero ⟶</a></div>
  <div class="p-fotos"><div style="background-image:url({madre})"></div><div style="background-image:url({familia})"></div>
   <div class="ancha" style="background-image:url({trab})"></div></div>
 </div>
 <div class="p-nav"><div class="eti">EXPLORE LAS SECCIONES</div><div class="botones">{botones}</div></div>
</div>
<div class="app" id="app">
 <nav class="lateral"><img src="{logo}" alt="UAO"><div class="eti">SECCIONES</div>{menu}<a class="volver" href="#portada">⟵ Portada</a></nav>
 <main>{paginas}</main>
</div>
<script>
const FIG = {figs};
const CONF = {{displayModeBar:false, responsive:true}};
const dibujados = new Set();
function dibujar(id, fig){{ const el = document.getElementById('g_'+id); if(!el) return;
  Plotly.react(el, fig.data, fig.layout, CONF); dibujados.add(id); }}
function dibujarPagina(p){{ document.querySelectorAll('#p_'+p+' .graf').forEach(el => {{
  const id = el.id.slice(2);
  if (id === 'piramide') dibujar(id, FIG.piramide[document.getElementById('sel_pir').value]);
  else if (id === 'flp') dibujar(id, FIG.flp[document.getElementById('sel_flp').value]);
  else dibujar(id, FIG[id]); }}); }}
function ir(){{ const p = (location.hash || '#portada').slice(1);
  const enPortada = !document.getElementById('p_'+p);
  document.getElementById('portada').style.display = enPortada ? 'flex' : 'none';
  document.getElementById('app').classList.toggle('activa', !enPortada);
  document.querySelectorAll('.pagina').forEach(s => s.classList.toggle('activa', s.id === 'p_'+p));
  document.querySelectorAll('nav.lateral a[data-p]').forEach(a => a.classList.toggle('actual', a.dataset.p === p));
  if(!enPortada){{ window.scrollTo(0,0); requestAnimationFrame(() => dibujarPagina(p)); }} }}
document.getElementById('sel_pir').addEventListener('change', e => dibujar('piramide', FIG.piramide[e.target.value]));
document.getElementById('sel_flp').addEventListener('change', e => dibujar('flp', FIG.flp[e.target.value]));
window.addEventListener('hashchange', ir); ir();
</script>
</body></html>
"""

if __name__ == "__main__":
    construir()
