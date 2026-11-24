"""Pruebas de herramienta_apriltag: del tag creado al tag leído, sin cámara ni hardware."""

import json
import math
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import herramienta_apriltag as h  # noqa: E402

LADO_M = 0.06
FOV_H = 60.0
ANCHO, ALTO = 640, 480


@pytest.fixture(scope="module")
def detector():
    return h.crear_detector("tag36h11")


def en_lienzo(tag: np.ndarray) -> np.ndarray:
    """Pega el tag (con su margen) en el centro de una imagen de cámara."""
    lienzo = np.full((ALTO, ANCHO), 200, np.uint8)
    y, x = (ALTO - tag.shape[0]) // 2, (ANCHO - tag.shape[1]) // 2
    lienzo[y : y + tag.shape[0], x : x + tag.shape[1]] = tag
    return lienzo


# ---------------------------------------------------------------- crear → leer


@pytest.mark.parametrize("familia", list(h.FAMILIAS))
def test_cada_id_creado_se_lee_con_el_mismo_numero(familia):
    det = h.crear_detector(familia)
    total = h.ids_validos(familia)
    for tag_id in sorted({0, 1, total // 2, total - 1}):
        escena = en_lienzo(h.imagen_png(familia, tag_id, px_celda=12))
        leidos = h.detectar_en(det, escena)
        assert [d["id"] for d in leidos] == [tag_id], f"{familia} id {tag_id}"


def test_familias_tienen_los_ids_esperados():
    assert h.ids_validos("tag36h11") == 587
    assert h.ids_validos("tag25h9") == 35
    assert h.ids_validos("tag16h5") == 30


def test_tags_distintos_dan_cuadriculas_distintas():
    cuadriculas = {h.matriz_tag("tag36h11", i).tobytes() for i in range(50)}
    assert len(cuadriculas) == 50


def test_ida_y_vuelta_por_archivo(tmp_path, detector):
    """Crear -> guardar PNG en disco -> leer del disco -> detectar."""
    ruta = tmp_path / "tag.png"
    h.guardar_png(ruta, h.imagen_png("tag36h11", 42, px_celda=20))
    leida = cv2.cvtColor(h.leer_imagen(ruta), cv2.COLOR_BGR2GRAY)
    assert [d["id"] for d in h.detectar_en(detector, en_lienzo(leida))] == [42]


def test_varios_tags_en_una_misma_imagen(detector):
    escena = h.componer_escena("tag36h11", [5, 9, 100])
    assert sorted(d["id"] for d in h.detectar_en(detector, escena)) == [5, 9, 100]


def test_sin_tags_no_detecta_nada(detector):
    assert h.detectar_en(detector, np.full((ALTO, ANCHO), 128, np.uint8)) == []


def test_id_fuera_de_rango_es_error_claro():
    with pytest.raises(h.ErrorHerramienta, match="0 a 586"):
        h.matriz_tag("tag36h11", 587)
    with pytest.raises(h.ErrorHerramienta):
        h.matriz_tag("tag36h11", -1)


def test_expandir_ids():
    assert h._expandir_ids("3") == [3]
    assert h._expandir_ids("0-3") == [0, 1, 2, 3]
    assert h._expandir_ids("1,5,9") == [1, 5, 9]
    with pytest.raises(h.ErrorHerramienta):
        h._expandir_ids("abc")


# --------------------------------------------------------------------- SVG


def _celdas_del_svg(svg: str, n: int) -> np.ndarray:
    rejilla = np.zeros((n, n), np.uint8)
    for x, y, ancho in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="1"/>', svg):
        x, y, ancho = int(x) - h.MARGEN_CELDAS, int(y) - h.MARGEN_CELDAS, int(ancho)
        rejilla[y, x : x + ancho] = 1
    return rejilla


@pytest.mark.parametrize("familia", list(h.FAMILIAS))
def test_el_svg_dibuja_exactamente_el_mismo_tag(familia):
    matriz = h.matriz_tag(familia, 3)
    svg = h.svg_tag(familia, 3, 60.0)
    assert np.array_equal(_celdas_del_svg(svg, matriz.shape[0]), matriz)


def test_el_svg_tiene_el_tamano_real_en_mm():
    svg = h.svg_tag("tag36h11", 0, 60.0)
    # 8 celdas = 60 mm; con 2 celdas de margen por lado son 12 celdas = 90 mm
    assert 'width="90.000mm"' in svg and 'height="90.000mm"' in svg
    assert 'viewBox="0 0 12 12"' in svg


# --------------------------------------------------------------------- pose


def parametros():
    return h.parametros_camara(ANCHO, ALTO, fov_h=FOV_H)


def test_parametros_de_camara_desde_el_campo_de_vision():
    fx, fy, cx, cy = parametros()
    assert fx == pytest.approx(320 / math.tan(math.radians(30)))
    assert (fx, cx, cy) == (fy, 320, 240)


def test_parametros_explicitos_ganan_al_fov():
    assert h.parametros_camara(640, 480, fx=500, fov_h=60) == (500, 500, 320, 240)
    assert h.parametros_camara(640, 480) is None
    with pytest.raises(h.ErrorHerramienta):
        h.parametros_camara(640, 480, fov_h=200)


def test_distancia_z_coincide_con_la_geometria(detector):
    """Un tag de 6 cm que ocupa 80 px con fx conocido está a z = fx * L / px."""
    px_celda = 10
    escena = en_lienzo(h.imagen_png("tag36h11", 7, px_celda))
    d = h.detectar_en(detector, escena, parametros(), LADO_M)[0]
    z_esperada = parametros()[0] * LADO_M / (8 * px_celda)
    assert d["pose"]["z"] == pytest.approx(z_esperada, rel=0.03)
    assert abs(d["pose"]["x"]) < 0.01 and abs(d["pose"]["y"]) < 0.01
    assert abs(d["pose"]["dth"]) < 3


def test_sin_tamano_o_camara_no_hay_pose(detector):
    escena = en_lienzo(h.imagen_png("tag36h11", 7, 10))
    assert h.detectar_en(detector, escena)[0]["pose"] is None
    assert h.detectar_en(detector, escena, parametros(), None)[0]["pose"] is None


def render_con_giro(grados: float, z0: float = 0.5, px_celda: int = 40) -> np.ndarray:
    """Dibuja el tag como lo vería la cámara si girara `grados` alrededor del eje vertical."""
    tag = h.imagen_png("tag36h11", 7, px_celda)
    celdas_total = 8 + 2 * h.MARGEN_CELDAS
    a = LADO_M * celdas_total / 8 / 2  # semilado de la imagen completa, en metros
    th = math.radians(grados)
    fx, fy, cx, cy = parametros()
    destino = []
    for x, y in ((-a, -a), (a, -a), (a, a), (-a, a)):
        X, Y, Z = x * math.cos(th), y, z0 - x * math.sin(th)
        destino.append((fx * X / Z + cx, fy * Y / Z + cy))
    alto, ancho = tag.shape
    origen = np.float32([(0, 0), (ancho, 0), (ancho, alto), (0, alto)])
    H = cv2.getPerspectiveTransform(origen, np.float32(destino))
    return cv2.warpPerspective(tag, H, (ANCHO, ALTO), borderValue=200)


@pytest.mark.parametrize("grados", [-35, -20, 20, 35])
def test_el_giro_dth_se_recupera_con_su_signo(grados, detector):
    d = h.detectar_en(detector, render_con_giro(grados), parametros(), LADO_M)[0]
    assert d["pose"]["dth"] == pytest.approx(grados, abs=4)
    assert d["pose"]["z"] == pytest.approx(0.5, rel=0.05)


# ----------------------------------------------------------------- línea de comandos


def test_autoprueba_sale_con_cero(capsys):
    assert h.main(["autoprueba"]) == 0
    assert "OK" in capsys.readouterr().out


def test_crear_escribe_png_y_svg(tmp_path):
    assert h.main(["crear", "--id", "0-1", "--salida", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "tag36h11_id000.png",
        "tag36h11_id000.svg",
        "tag36h11_id001.png",
        "tag36h11_id001.svg",
    ]


def test_detectar_imagen_imprime_json_y_guarda_anotada(tmp_path, capsys):
    ruta = tmp_path / "escena.png"
    h.guardar_png(ruta, h.componer_escena("tag36h11", [4, 8]))
    anotada = tmp_path / "anotada.png"
    codigo = h.main(["detectar", "--imagen", str(ruta), "--anotada", str(anotada)])
    lineas = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert codigo == 0
    assert sorted(json.loads(line)["id"] for line in lineas) == [4, 8]
    assert anotada.is_file()


def test_detectar_sin_tags_sale_con_codigo_2(tmp_path):
    ruta = tmp_path / "vacia.png"
    h.guardar_png(ruta, np.full((100, 100), 128, np.uint8))
    assert h.main(["detectar", "--imagen", str(ruta)]) == 2


def test_detectar_video(tmp_path, capsys):
    ruta = tmp_path / "video.avi"
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"MJPG"), 10, (ANCHO, ALTO))
    cuadro = cv2.cvtColor(en_lienzo(h.imagen_png("tag36h11", 11, 10)), cv2.COLOR_GRAY2BGR)
    for _ in range(5):
        escritor.write(cuadro)
    escritor.release()
    codigo = h.main(["detectar", "--video", str(ruta), "--tamano-mm", "60", "--fov-h", "60"])
    lineas = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert codigo == 0 and len(lineas) == 5
    assert '"id": 11' in lineas[0] and '"pose": {' in lineas[0]


def test_fuente_inexistente_es_error_sin_traza(capsys):
    assert h.main(["detectar", "--imagen", "no_existe.png"]) == 1
    assert "no existe la imagen" in capsys.readouterr().err
    assert h.main(["detectar", "--video", "no_existe.avi"]) == 1
