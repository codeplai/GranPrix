"""MqttGateway sin broker: se le entregan tópico y payload en bruto, como los entregaría aiomqtt."""

import json

import pytest

from pc_race.adaptadores.entrada.mqtt_gateway import MqttGateway
from pc_race.aplicacion.casos_de_uso.iniciar_tanda import IniciarTanda
from pc_race.aplicacion.metricas import Metricas
from pc_race.aplicacion.monitor_latidos import MonitorLatidos
from pc_race.dominio.tanda import Fase


@pytest.fixture
def metricas():
    return Metricas()


@pytest.fixture
def monitor(tablero):
    return MonitorLatidos(tablero)


@pytest.fixture
def gateway(sesion, metricas, monitor, reloj):
    return MqttGateway(sesion, metricas, monitor, reloj)


@pytest.fixture
async def en_carrera(sesion):
    await IniciarTanda(sesion).nueva([7, 8], con_calentamiento=False)
    return sesion


def js(**campos):
    return json.dumps({"v": 1, **campos})


async def pit(gateway, equipo, estacion, ts, ok=True):
    base = f"granprix/estacion/{estacion}"
    pose = {"dx": 0.03, "dy": 0.04, "dth": 1}
    await gateway.procesar(
        f"{base}/solicitud",
        js(ts=ts - 2, equipo=equipo, dock=estacion, pose=pose, pieza_trae="A"),
    )
    await gateway.procesar(
        f"{base}/resultado", js(ts=ts, equipo=equipo, ok=ok, pieza_dejo="B", t_cambio=5.8)
    )


async def test_una_vuelta_entera_por_mqtt(gateway, en_carrera, metricas):
    for i, estacion in enumerate((1, 2, 3, 4)):
        await pit(gateway, 7, estacion, 1_010.0 + 10 * i)
    await gateway.procesar(
        "granprix/eq07/vuelta", js(ts=1_050.0, equipo=7, numero=1, t_inicio=1_000.0, t_fin=1_045.0)
    )

    resumen = {r.equipo: r for r in en_carrera.tanda.resumenes()}[7]
    assert resumen.vueltas_validas == 1
    assert resumen.error_pose_medio == pytest.approx(0.05)
    assert metricas.total_invalidos == 0


async def test_intervencion_declarada_del_carrito(gateway, en_carrera):
    await gateway.procesar(
        "granprix/eq07/evento",
        js(ts=1_300.5, equipo=7, tipo="intervencion", subtipo="fisica", declarada=True),
    )
    assert {r.equipo: r for r in en_carrera.tanda.resumenes()}[7].puntos_intervencion == 1


async def test_mismo_evento_entregado_dos_veces_cuenta_una_vez(gateway, en_carrera):
    mensaje = js(ts=1_300.5, equipo=7, tipo="intervencion", subtipo="web", declarada=True)
    await gateway.procesar("granprix/eq07/evento", mensaje)
    await gateway.procesar("granprix/eq07/evento", mensaje)
    assert {r.equipo: r for r in en_carrera.tanda.resumenes()}[7].puntos_intervencion == 1


async def test_pit_ok_y_reintento_son_informativos(gateway, en_carrera, metricas):
    await gateway.procesar("granprix/eq07/evento", js(ts=1_100.0, equipo=7, tipo="pit_ok"))
    await gateway.procesar("granprix/eq07/evento", js(ts=1_101.0, equipo=7, tipo="reintento"))
    assert {r.equipo: r for r in en_carrera.tanda.resumenes()}[7].puntos_intervencion == 0
    assert metricas.total_invalidos == 0


@pytest.mark.parametrize(
    ("topico", "payload"),
    [
        ("granprix/eq07/evento", "esto no es json"),
        ("granprix/eq07/evento", js(ts=1.0, equipo=7, tipo="intervencion")),  # sin subtipo
        ("granprix/eq07/evento", json.dumps({"v": 9, "ts": 1.0, "equipo": 7, "tipo": "pit_ok"})),
        ("granprix/eq07/evento", js(ts=1.0, equipo=8, tipo="pit_ok")),  # equipo distinto al tópico
        (
            "granprix/estacion/2/solicitud",
            js(ts=1.0, equipo=7, dock=3, pose={"dx": 0, "dy": 0, "dth": 0}),  # dock distinto
        ),
        ("granprix/eq07/vuelta", js(ts=1.0, equipo=7, numero="uno", t_inicio=0, t_fin=1)),
        ("granprix/eq07/desconocido", "{}"),
    ],
)
async def test_mensaje_invalido_se_descarta_y_se_cuenta_sin_romper_nada(
    gateway, en_carrera, metricas, topico, payload
):
    await gateway.procesar(topico, payload)
    assert metricas.total_invalidos == 1
    assert en_carrera.tanda.fase is Fase.CARRERA
    await gateway.procesar(  # y el gateway sigue funcionando
        "granprix/eq07/evento", js(ts=1_400.0, equipo=7, tipo="intervencion", subtipo="web")
    )
    assert {r.equipo: r for r in en_carrera.tanda.resumenes()}[7].puntos_intervencion == 1


async def test_vuelta_con_hora_incoherente_se_descarta_sin_error_interno(
    gateway, en_carrera, metricas
):
    await gateway.procesar(
        "granprix/eq07/vuelta", js(ts=1_050.0, equipo=7, numero=1, t_inicio=1_045.0, t_fin=1_000.0)
    )
    assert metricas.descartados["VueltaInvalida"] == 1
    assert "error_interno" not in metricas.descartados


async def test_equipo_fuera_de_la_tanda_se_descarta(gateway, en_carrera, metricas):
    await gateway.procesar(
        "granprix/eq09/evento", js(ts=1.0, equipo=9, tipo="intervencion", subtipo="web")
    )
    assert metricas.descartados["EquipoDesconocido"] == 1


async def test_mensajes_sin_tanda_se_descartan(gateway, metricas):
    await gateway.procesar(
        "granprix/eq07/evento", js(ts=1.0, equipo=7, tipo="intervencion", subtipo="web")
    )
    assert metricas.descartados["SinTandaActiva"] == 1


async def test_estado_de_estacion_texto_plano_del_last_will(gateway, tablero):
    await gateway.procesar("granprix/estacion/2/estado", "OFFLINE")
    assert any("estacion:2 OFFLINE" in a for a in tablero.avisos)


async def test_estado_de_estacion_json_es_latido(gateway, tablero, metricas):
    await gateway.procesar("granprix/estacion/2/estado", js(ts=1.0, estado="LIBRE"))
    assert metricas.total_invalidos == 0 and not tablero.avisos


async def test_telemetria_cuenta_como_latido_del_carrito(gateway, monitor, reloj, tablero):
    await gateway.procesar("granprix/eq07/telemetria", js(ts=1.0, equipo=7, bateria=80.0))
    reloj.avanzar(4)
    assert await monitor.revisar(reloj.ahora()) == ["carrito:7"]
    assert any("carrito:7 OFFLINE" in a for a in tablero.avisos)


async def test_conteo_de_recibidos(gateway, metricas):
    await gateway.procesar("granprix/eq07/telemetria", js(ts=1.0, equipo=7))
    await gateway.procesar("basura", "x")
    assert metricas.recibidos == 2
