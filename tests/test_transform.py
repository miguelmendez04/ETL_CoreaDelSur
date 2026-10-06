"""Pruebas de silver y gold con datos sintéticos pequeños (sin base de datos)."""
import pandas as pd
import pytest

from src.transform.gold import escenarios, riesgo
from src.quality import validate
from src.transform.silver import derive, homologacion

DIMS = homologacion.cargar_dimensiones()


def _fila(**kw):
    base = {"nivel": "historico", "anio": 2020, "territorio_src": "Seoul", "sexo_src": "Total", "edad_src": "Total",
            "escenario_src": None, "cod_indicador": "POBLACION", "valor_txt": "100", "factor": 1, "fuente": "KOSIS",
            "dataset": "prueba", "tabla_origen": "bronze.kosis", "id_bronze": 1, "id_carga_origen": 1,
            "fecha_extraccion": pd.Timestamp("2026-10-01"), "edicion_proyeccion": None, "version_publicacion": "v"}
    return {**base, **kw}


@pytest.mark.parametrize("etiqueta, esperado", [
    ("0 - 4세", "0-4"), ("0-4 Years old", "0-4"), ("50-59 Yeras old", "50-59"), ("100세 이상", "100+"),
    ("100 Years old & over", "100+"), ("60 Years old and over", "60+"), ("80세이상", "80+"), ("계", "TOTAL"),
    ("Total", "TOTAL"), ("15+", "15+"), ("cualquier cosa", None)])
def test_normalizar_edad(etiqueta, esperado):
    assert homologacion.normalizar_edad(etiqueta) == esperado


def test_homologar_mapea_coreano_y_rechaza_lo_desconocido():
    cfg = {"silver": {"edades_excluidas": ["80+"], "edades_agrupadas": {"85-89": "85+"}}}
    cand = pd.DataFrame([
        _fila(sexo_src="남자", edad_src="0 - 4세"),
        _fila(territorio_src="sejong-si", sexo_src="여자", edad_src="85 - 89세"),
        _fila(territorio_src="Jeonnam-Gwangju"),
        _fila(territorio_src="Atlántida"),
        _fila(edad_src="80세이상"),
    ])
    ok, rech, fuera = homologacion.homologar(cand, DIMS, cfg)
    assert ok[["cod_territorio", "sexo", "grupo_edad"]].values.tolist() == [["11", "H", "0-4"], ["29", "M", "85+"]]
    assert sorted(rech["regla"]) == ["etiqueta_no_mapeada", "territorio_excluido"]
    assert fuera["edad_agregada_solapada"] == 1


def _homologado(**kw):
    f = _fila(**kw)
    f.update(cod_territorio=kw.get("cod_territorio", "11"), sexo=kw.get("sexo", "T"),
             grupo_edad=kw.get("grupo_edad", "TOTAL"), escenario="-")
    f["edicion_proyeccion"] = "-"
    return f


def test_convertir_valores_distingue_nulo_de_no_aplica():
    df = pd.DataFrame([
        _homologado(valor_txt="12", factor=1000),
        _homologado(valor_txt="-"),                                   # nulo real: rechazo
        _homologado(valor_txt="-", cod_territorio="29", anio=2005),   # Sejong antes de 2012: no aplica
        _homologado(valor_txt="abc"),                                 # no numérico: rechazo
    ])
    ok, rech, no_aplica = validate.convertir_valores(df, DIMS)
    assert ok["valor"].tolist() == [12000]
    assert sorted(rech["regla"]) == ["nulo", "tipo_invalido"] and no_aplica == 1


def test_validar_rango_indicador_y_duplicados():
    df = pd.DataFrame([_homologado(cod_indicador="TFR"), _homologado(cod_indicador="TFR"),
                       _homologado(cod_indicador="TFR", anio=2021), _homologado(cod_indicador="NO_EXISTE")])
    df["valor"] = [1.1, 1.1, 12.0, 5.0]
    ok, rech = validate.validar(df, DIMS)
    assert len(ok) == 1
    assert sorted(rech["regla"]) == ["clave_duplicada", "indicador_invalido", "rango"]


def _silver(filas):
    df = pd.DataFrame(filas)
    for c, v in {"nivel": "historico", "sexo": "T", "edicion_proyeccion": "-", "escenario": "-", "fuente": "KOSIS",
                 "fecha_extraccion": pd.Timestamp("2026-10-01"), "version_publicacion": "v", "id_carga_origen": 1}.items():
        if c not in df:
            df[c] = v
    return df


EAPS = ["15-19", "20-29", "30-39", "40-49", "50-59", "60+"]
REGLAS_COHERENCIA = {"POBLACION": {"total": "TOTAL", "redondeo": 1, "grupos": ["0-4", "5-9", "10-14"]},
                     "POB_ACTIVA": {"total": "15+", "redondeo": 1000, "grupos": EAPS}}


def test_coherencia_rechaza_total_que_no_cuadra():
    filas = [{"anio": 2020, "cod_territorio": "11", "cod_indicador": "POBLACION", "grupo_edad": g, "valor": 10.0}
             for g in ["0-4", "5-9", "10-14"]]
    filas.append({"anio": 2020, "cod_territorio": "11", "cod_indicador": "POBLACION", "grupo_edad": "TOTAL", "valor": 999.0})
    ok, rech = validate.coherencia_totales(_silver(filas), 0.5, REGLAS_COHERENCIA)
    assert rech["regla"].tolist() == ["coherencia_totales"] and "TOTAL" not in ok["grupo_edad"].values


def test_coherencia_eaps_tolera_redondeo_a_miles_pero_no_descuadres():
    def eaps(anio, h_1519, total_1519, total_15mas):
        f = [{"anio": anio, "sexo": "T", "grupo_edad": g, "valor": 1_000_000.0} for g in EAPS[1:]]
        f += [{"anio": anio, "sexo": "T", "grupo_edad": "15-19", "valor": total_1519},
              {"anio": anio, "sexo": "H", "grupo_edad": "15-19", "valor": h_1519},
              {"anio": anio, "sexo": "M", "grupo_edad": "15-19", "valor": 84_000.0},
              {"anio": anio, "sexo": "T", "grupo_edad": "15+", "valor": total_15mas}]
        return [{**x, "cod_territorio": "00", "cod_indicador": "POB_ACTIVA"} for x in f]
    # 2025: H + M = 144 mil vs T = 143 mil (0,7 %, pero es redondeo a miles) -> se acepta
    # 2024: H + M = 184 mil vs T = 143 mil y grupos 5,143 M vs 15+ 5,5 M -> se rechazan ambos totales
    df = _silver(eaps(2025, 60_000.0, 143_000.0, 5_143_000.0) + eaps(2024, 100_000.0, 143_000.0, 5_500_000.0))
    ok, rech = validate.coherencia_totales(df, 0.5, REGLAS_COHERENCIA)
    assert len(rech) == 2 and all(r["anio"] == 2024 for r in rech["registro"])
    assert len(ok) == len(df) - 2


def test_derivados_y_agregados_de_edad():
    filas = [{"anio": 2020, "cod_territorio": "00", "cod_indicador": "POBLACION", "grupo_edad": g, "valor": v}
             for g, v in [("0-4", 5), ("5-9", 5), ("10-14", 10), ("TOTAL", 100)]]
    filas += [{"anio": 2020, "cod_territorio": "00", "cod_indicador": "POBLACION", "grupo_edad": "15-64", "valor": 60},
              {"anio": 2020, "cod_territorio": "00", "cod_indicador": "POBLACION", "grupo_edad": "65+", "valor": 20}]
    df = derive.agregados_edad(_silver(filas), {"0-14": ["0-4", "5-9", "10-14"]})
    df = derive.derivados(df)
    v = df.set_index("cod_indicador")["valor"]
    assert df.loc[df["grupo_edad"] == "0-14", "valor"].item() == 20
    assert v["PROP_65MAS"] == 20 and v["INDICE_ENVEJECIMIENTO"] == 100 and v["DEPENDENCIA_VEJEZ"] == pytest.approx(33.333, 1e-3)


def test_chungnam_sejong_suma_niveles_y_recalcula_tasas():
    filas = []
    for terr, pob15, activa, ocup in [("34", 1000, 600, 570), ("29", 200, 140, 136)]:
        filas += [{"anio": 2020, "cod_territorio": terr, "grupo_edad": "15+", "cod_indicador": i, "valor": v}
                  for i, v in [("POB_15MAS", pob15), ("POB_ACTIVA", activa), ("OCUPADOS", ocup)]]
    regla = {"codigo": "CNSJ", "componentes": ["34", "29"], "indicadores_suma": ["POB_15MAS", "POB_ACTIVA", "OCUPADOS"]}
    out = derive.chungnam_sejong(_silver(filas), regla)
    cnsj = out[out["cod_territorio"] == "CNSJ"].set_index("cod_indicador")["valor"]
    assert cnsj["POB_ACTIVA"] == 740
    assert cnsj["TASA_PARTICIPACION"] == round(740 / 1200 * 100, 1)
    assert cnsj["TASA_DESEMPLEO"] == round((740 - 706) / 740 * 100, 1)


def _cfg_escenarios():
    return {"silver": {"ediciones": {"kosis_nacional": "E"}},
            "gold": {"version_modelo": "t", "escenarios_fuerza_laboral": {
                "anio_base": 2025, "grupos": {"30-39": ["30-34", "35-39"]},
                "supuestos": {
                    "A": {"nombre": "a", "descripcion": "a"},
                    "B": {"nombre": "b", "descripcion": "b", "anios_tendencia": [2015, 2025], "cambio_maximo_pp": 5,
                          "piso": 0, "tope": 90, "congelar_desde": 2050},
                    "C": {"nombre": "c", "descripcion": "c", "anio_convergencia": 2035,
                          "equivalencias_oecd": {"30-39": {"Y25T54": 1}}}}}}}


def test_escenarios_a_b_c():
    hist = pd.DataFrame([{"cod_territorio": "00", "sexo": "M", "cod_indicador": "TASA_PARTICIPACION",
                          "grupo_edad": "30-39", "anio": a, "valor": 50 + (a - 2015)} for a in range(2015, 2026)] +
                        [{"cod_territorio": "OED", "sexo": "M", "cod_indicador": "TASA_PARTICIPACION",
                          "grupo_edad": "25-54", "anio": 2024, "valor": 80.0},
                         {"cod_territorio": "00", "sexo": "H", "cod_indicador": "TASA_PARTICIPACION",
                          "grupo_edad": "30-39", "anio": 2025, "valor": 90.0}])
    proy = pd.DataFrame([{"cod_territorio": "00", "sexo": s, "cod_indicador": "POBLACION", "edicion_proyeccion": "E",
                          "escenario": "medio", "grupo_edad": g, "anio": a, "valor": 1000}
                         for s in "HM" for g in ["30-34", "35-39"] for a in (2030, 2035, 2040)])
    esc, sup = escenarios.calcular(hist, proy, _cfg_escenarios())
    t = esc[esc["sexo"] == "M"].set_index(["id_supuesto", "anio"])["tasa_participacion"]
    assert t[("A", 2040)] == 60                     # constante
    assert t[("B", 2030)] == pytest.approx(65) and t[("B", 2040)] == pytest.approx(65)   # +1 pp/año, acotado a +5 pp
    assert t[("C", 2030)] == pytest.approx(70) and t[("C", 2035)] == pytest.approx(80)   # converge a la OCDE en 2035
    assert t[("C", 2040)] == pytest.approx(80)
    assert sup.set_index("id_supuesto").loc["C", "parametros"]["constantes_por_falta_de_dato_oecd"] == ["H,30-39"]
    fila = esc[(esc["sexo"] == "M") & (esc["id_supuesto"] == "A") & (esc["anio"] == 2030)].iloc[0]
    assert fila["poblacion"] == 2000 and fila["fuerza_laboral"] == 1200
    assert set(sup["id_supuesto"]) == {"A", "B", "C"}


def test_riesgo_normaliza_y_ordena():
    hist = pd.DataFrame([{"cod_territorio": t, "sexo": "T", "cod_indicador": i, "grupo_edad": g, "anio": a, "valor": v}
                         for t, p65, tfr in [("11", 20, 0.6), ("21", 30, 0.8)]
                         for i, g, a, v in [("PROP_65MAS", "TOTAL", 2025, p65), ("TFR", "TOTAL", 2025, tfr),
                                            ("POBLACION", "15-64", 2025, 100), ("POBLACION", "15-64", 2015, 110)]])
    proy = pd.DataFrame([{"cod_territorio": t, "sexo": "T", "cod_indicador": "POBLACION", "grupo_edad": "15-64",
                          "anio": 2052, "valor": v, "edicion_proyeccion": "S", "escenario": "medio"} for t, v in [("11", 60), ("21", 70)]])
    dims = pd.DataFrame({"cod_territorio": ["11", "21"], "tipo": ["sido", "sido"]})
    cfg = {"silver": {"ediciones": {"kosis_sido": "S"}},
           "gold": {"riesgo_sido": {"anio_base": 2025, "anio_proyeccion": 2052, "componentes": {
               "prop_65mas": {"peso": 1, "mas_es_peor": True}, "tfr": {"peso": 1, "mas_es_peor": False}}}}}
    r = riesgo.calcular(hist, proy, dims, cfg).set_index("cod_territorio")
    assert r.loc["21", "indice_riesgo"] == 50 and r.loc["11", "indice_riesgo"] == 50   # cada uno peor en un componente
    assert r.loc["11", "var_pob_15_64_proy_pct"] == -40


def test_factor_cobertura_reproduce_la_poblacion_eaps():
    hist = pd.DataFrame([{"cod_territorio": "00", "sexo": "M", "anio": 2025, "cod_indicador": "POBLACION",
                          "grupo_edad": g, "valor": 500.0} for g in ("30-34", "35-39")] +
                        [{"cod_territorio": "00", "sexo": "M", "anio": 2025, "cod_indicador": "POB_15MAS",
                          "grupo_edad": "30-39", "valor": 900.0}])
    f = escenarios.factor_cobertura(hist, {"30-39": ["30-34", "35-39"]}, 2025)
    assert f["factor_cobertura"].item() == pytest.approx(0.9)


def test_asociaciones_distingue_tendencia_de_comovimiento():
    from src.transform.gold import analisis
    # Ambas crecen (correlación alta en niveles) pero sus variaciones anuales no se mueven juntas.
    anios = range(2000, 2010)
    dx = [1, 2, 1, 2, 1, 2, 1, 2, 1]
    dy = [2, 2, 1, 1, 2, 2, 1, 1, 2]
    x = [10 + sum(dx[:i]) for i in range(10)]
    y = [5 + sum(dy[:i]) for i in range(10)]
    hist = pd.DataFrame([{"cod_territorio": "00", "sexo": "T", "cod_indicador": i, "grupo_edad": "TOTAL", "anio": a, "valor": v}
                         for i, serie in (("PROP_65MAS", x), ("PIB_HORA", y)) for a, v in zip(anios, serie)])
    r = analisis.asociaciones(hist, [["PROP_65MAS", "PIB_HORA"]]).iloc[0]
    assert r["corr_niveles"] > 0.9 and abs(r["corr_variaciones"]) < 0.3 and r["n"] == 10


def test_sensibilidad_riesgo_conserva_direccion_y_ordena():
    t = pd.DataFrame({"cod_territorio": ["A", "B"], "prop_65mas": [10, 20], "tfr": [1.0, 0.5]})
    cfg = {"gold": {"riesgo_sido": {"componentes": {"prop_65mas": {"peso": 1, "mas_es_peor": True},
                                                    "tfr": {"peso": 1, "mas_es_peor": False}},
                                    "esquemas_sensibilidad": {"solo_tfr": {"tfr": 1}}}}}
    s = riesgo.sensibilidad(t, cfg).set_index(["esquema", "cod_territorio"])["ranking"]
    assert s[("base", "B")] == 1 and s[("solo_tfr", "B")] == 1 and s[("solo_tfr", "A")] == 2


def test_normalizacion_percentil_no_depende_del_valor_extremo():
    # D es extremo en prop_65mas: con min-max comprime a A, B y C; con percentil solo cuenta el orden.
    t = pd.DataFrame({"prop_65mas": [10.0, 11.0, 12.0, 100.0], "tfr": [0.8, 1.0, 0.9, 1.2]}, index=list("ABCD"))
    comps = {"prop_65mas": {"peso": 1, "mas_es_peor": True}, "tfr": {"peso": 1, "mas_es_peor": False}}
    p = riesgo.indice(t, comps, "percentil")
    assert p.tolist() == pytest.approx([50, 33.333, 66.667, 50], abs=1e-3)   # C pasa a ser el de mayor riesgo
    assert riesgo.indice(t, comps)["C"] < riesgo.indice(t, comps)["A"]   # en min-max el extremo cambia el orden de C


def test_pasos_embudo_marca_filtros_y_calculos():
    from src.transform.silver.ejecutar import pasos_embudo
    p = pasos_embudo([("Formato largo", "filtro", 100, ""), ("Homologados", "filtro", 90, ""),
                      ("+ derivados", "calculo", 120, ""), ("Coherencia", "filtro", 118, "")])
    assert p["orden"].tolist() == [1, 2, 3, 4] and p["variacion"].tolist() == [0, -10, 30, -2]
    assert p["en_embudo"].tolist() == [True, True, False, False]   # después de un cálculo ya no es embudo
    with pytest.raises(ValueError, match="agregó filas"):
        pasos_embudo([("A", "filtro", 10, ""), ("B", "filtro", 12, "")])
