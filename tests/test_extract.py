"""Pruebas de la capa bronze sin red ni base de datos: crudos en una carpeta temporal."""
import pytest

from src.extract import comun, kosis

CFG = {"kosis": {
    "url_portal": "https://kosis.kr/eng/",
    "url_tabla": "https://kosis.kr/statHtml/statHtml.do?orgId={org_id}&tblId={tbl_id}",
    "archivos": {
        "doble": {"patron": "doble_*.csv", "tabla_kosis": "Tabla doble", "org_id": "101", "tbl_id": "DT_X",
                  "encoding": "utf-8-sig", "formato": "encabezado_doble", "columnas_dimension": ["By province"],
                  "periodo_esperado": {"inicio": 2000, "fin": 2002}},
        "ancho": {"patron": "ancho.csv", "tabla_kosis": "Tabla ancha", "org_id": "101", "tbl_id": None,
                  "encoding": "utf-8-sig", "formato": "ancho", "columnas_dimension": ["By items"]},
    }}}

DOBLE = ('"By province",2000,2000,2001,2001,2025.08\n'
         '"By province",Births,TFR,Births,TFR,Births\n'
         '"Seoul",100,0.9,90,0.8,7\n'
         '"Busan",50,1.0,-,0.9,3\n')


@pytest.fixture
def bronze(tmp_path, monkeypatch):
    monkeypatch.setattr(comun, "ruta", lambda clave: tmp_path)
    monkeypatch.setattr(kosis, "ruta", lambda clave: tmp_path)
    return tmp_path


def _escribir(bronze, carpeta, nombre, texto):
    destino = bronze / "kosis" / carpeta / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8-sig")
    return destino


def test_hash_registro_no_depende_del_orden_de_claves():
    assert comun.hash_registro({"a": 1, "b": "x"}) == comun.hash_registro({"b": "x", "a": 1})
    assert comun.hash_registro({"a": 1}) != comun.hash_registro({"a": 2})


def test_guardar_crudo_reutiliza_identico_y_nunca_sobrescribe(bronze):
    primero = comun.guardar_crudo("wb", "x.json", b"[1]")
    assert comun.guardar_crudo("wb", "x.json", b"[1]") == primero      # mismo contenido: no se duplica
    segundo = comun.guardar_crudo("wb", "x.json", b"[2]")              # contenido nuevo el mismo día
    assert segundo != primero and segundo.parent.name.startswith(primero.parent.name + "_")
    assert primero.read_bytes() == b"[1]" and segundo.read_bytes() == b"[2]"


def test_kosis_encabezado_doble_conserva_todo_tal_cual(bronze):
    _escribir(bronze, "2026-10-01", "doble_2000_2025.csv", DOBLE)
    ext = kosis.extraer("doble", CFG)
    assert ext.registros[1] == {"By province": "Busan", "2000 | Births": "50", "2000 | TFR": "1.0",
                                "2001 | Births": "-", "2001 | TFR": "0.9", "2025.08 | Births": "3"}
    assert ext.resumen["anios"] == "2000-2001" and ext.resumen["columnas_mensuales"] == 1
    assert ext.avisos == ["faltan años del periodo esperado: 2002-2002 (1)"]
    assert ext.columnas_extra == {"org_id": "101", "tbl_id": "DT_X"}
    assert ext.url.endswith("tblId=DT_X") and ext.fecha_extraccion.date().isoformat() == "2026-10-01"


def test_kosis_usa_la_descarga_mas_reciente(bronze):
    _escribir(bronze, "2026-09-01", "ancho.csv", '"By items",2000\n"Births",1\n')
    _escribir(bronze, "2026-10-01", "ancho.csv", '"By items",2000,2001\n"Births",1,2\n')
    ext = kosis.extraer("ancho", CFG)
    assert ext.archivo.parent.name == "2026-10-01" and ext.registros == [{"By items": "Births", "2000": "1", "2001": "2"}]


def test_kosis_rechaza_tabla_equivocada(bronze):
    _escribir(bronze, "2026-10-01", "ancho.csv", '"By gender",2000\n"Total",1\n')
    with pytest.raises(ValueError, match="columnas de dimensión"):
        kosis.extraer("ancho", CFG)


def test_kosis_sin_archivo_indica_que_descargar(bronze):
    with pytest.raises(FileNotFoundError, match="Tabla ancha"):
        kosis.extraer("ancho", CFG)
