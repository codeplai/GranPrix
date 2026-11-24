"""Cada ejemplo de 00-contrato-mqtt.md debe validar contra los modelos pydantic."""

import json

import pytest
from pydantic import ValidationError

from contrato import esquemas, modelos, topicos

EJEMPLO_SOLICITUD = """{ "v": 1, "ts": 1764001234.12, "equipo": 7, "dock": 2,
  "pose": {"dx": 0.021, "dy": -0.012, "dth": 1.8},
  "pieza_trae": "A" }"""
EJEMPLO_RESULTADO = """{ "v": 1, "ts": 1764001240.02, "equipo": 7, "ok": true,
  "pieza_dejo": "B", "t_cambio": 5.8 }"""
EJEMPLO_EVENTO = """{ "v": 1, "ts": 1764001300.50, "equipo": 7, "tipo": "intervencion",
  "subtipo": "fisica", "declarada": true }"""


def test_ejemplo_solicitud():
    m = modelos.SolicitudMsg.model_validate_json(EJEMPLO_SOLICITUD)
    assert (m.equipo, m.dock, m.pieza_trae, m.pose.dth) == (7, 2, "A", 1.8)


def test_ejemplo_resultado():
    m = modelos.ResultadoMsg.model_validate_json(EJEMPLO_RESULTADO)
    assert m.ok and m.pieza_dejo == "B" and m.t_cambio == 5.8


def test_ejemplo_evento():
    m = modelos.EventoMsg.model_validate_json(EJEMPLO_EVENTO)
    assert m.tipo == "intervencion" and m.subtipo == "fisica" and m.declarada


def test_campo_nuevo_se_ignora_sin_subir_la_version():
    m = modelos.ResultadoMsg.model_validate_json(
        '{"v": 1, "ts": 1.0, "equipo": 7, "ok": true, "campo_futuro": 123}'
    )
    assert m.ok


def test_version_desconocida_se_rechaza():
    with pytest.raises(ValidationError):
        modelos.ResultadoMsg.model_validate_json('{"v": 2, "ts": 1.0, "equipo": 7, "ok": true}')


def test_mensaje_sin_hora_se_rechaza():
    with pytest.raises(ValidationError):
        modelos.ResultadoMsg.model_validate_json('{"v": 1, "equipo": 7, "ok": true}')


def test_intervencion_sin_subtipo_se_rechaza():
    with pytest.raises(ValidationError):
        modelos.EventoMsg.model_validate_json(
            '{"v": 1, "ts": 1.0, "equipo": 7, "tipo": "intervencion"}'
        )


def test_subtipo_desconocido_se_rechaza():
    with pytest.raises(ValidationError):
        modelos.EventoMsg.model_validate_json(
            '{"v": 1, "ts": 1.0, "equipo": 7, "tipo": "intervencion", "subtipo": "magica"}'
        )


def test_los_mensajes_que_publica_race_control_son_json_valido():
    estado = modelos.EstadoCarreraMsg(
        ts=1.0, tanda="T1", fase=modelos.FaseMsg.CARRERA, equipos=[7, 8], t_carrera=12.5
    )
    assert json.loads(estado.model_dump_json())["fase"] == "carrera"
    assert json.loads(modelos.BanderaMsg(ts=1.0, bandera="roja").model_dump_json())["v"] == 1


@pytest.mark.parametrize(
    ("topico", "esperado"),
    [
        ("granprix/estacion/2/solicitud", ("estacion", 2, "solicitud")),
        ("granprix/estacion/4/estado", ("estacion", 4, "estado")),
        ("granprix/eq07/evento", ("carrito", 7, "evento")),
        ("granprix/eq10/telemetria", ("carrito", 10, "telemetria")),
    ],
)
def test_interpretar_topicos_de_entrada(topico, esperado):
    ruta = topicos.interpretar(topico)
    assert (ruta.origen, ruta.numero, ruta.canal) == esperado


@pytest.mark.parametrize(
    "topico",
    [
        "granprix/carrera/estado",  # lo publica Race Control, no lo escucha
        "granprix/eq7/evento",  # el número lleva dos dígitos
        "granprix/eq07/turno",
        "otra/cosa",
    ],
)
def test_topicos_ajenos_no_se_interpretan(topico):
    assert topicos.interpretar(topico) is None


def test_topicos_de_salida():
    assert topicos.topico_turno_carrito(7) == "granprix/eq07/turno"
    assert topicos.topico_turno_estacion(3) == "granprix/estacion/3/turno"


def test_json_schema_se_genera_para_todos_los_modelos(tmp_path):
    escritos = esquemas.generar(tmp_path)
    assert len(escritos) == len(esquemas.MODELOS)
    assert all(json.loads(p.read_text(encoding="utf-8"))["title"] for p in escritos)
