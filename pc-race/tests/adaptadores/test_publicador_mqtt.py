import json

import aiomqtt

from pc_race.adaptadores.salida.publicador_mqtt import PublicadorMqtt
from pc_race.dominio.bandera import Bandera
from pc_race.dominio.tanda import Fase


class ClienteFalso:
    def __init__(self, falla: bool = False) -> None:
        self.enviados: list[tuple[str, dict, int, bool]] = []
        self.falla = falla

    async def publish(self, topic, payload, qos=0, retain=False):
        if self.falla:
            raise aiomqtt.MqttError("broker caído")
        self.enviados.append((topic, json.loads(payload), qos, retain))


async def test_estado_se_publica_retenido_con_qos_1():
    cliente, pub = ClienteFalso(), PublicadorMqtt()
    await pub.conectar(cliente)
    await pub.publicar_estado("T1", Fase.CARRERA, [7, 8], 12.5, 100.0)

    topico, cuerpo, qos, retain = cliente.enviados[0]
    assert (topico, qos, retain) == ("granprix/carrera/estado", 1, True)
    assert cuerpo["fase"] == "carrera" and cuerpo["equipos"] == [7, 8] and cuerpo["v"] == 1


async def test_bandera_no_es_retenida():
    cliente, pub = ClienteFalso(), PublicadorMqtt()
    await pub.conectar(cliente)
    await pub.publicar_bandera(Bandera.ROJA, 100.0)
    assert cliente.enviados[0][0] == "granprix/carrera/bandera"
    assert cliente.enviados[0][2:] == (1, False)


async def test_turno_del_carrito_va_al_topico_eqnn():
    cliente, pub = ClienteFalso(), PublicadorMqtt()
    await pub.conectar(cliente)
    await pub.publicar_turno_carrito(7, True, "T1", 100.0)
    assert cliente.enviados[0][0] == "granprix/eq07/turno"
    assert cliente.enviados[0][1]["autorizado"] is True


async def test_sin_broker_guarda_y_al_reconectar_publica_el_ultimo_retenido_y_las_banderas():
    pub = PublicadorMqtt()  # nunca conectado
    await pub.publicar_estado("T1", Fase.CARRERA, [7], 0.0, 1.0)
    await pub.publicar_estado("T1", Fase.ROJA, [7], 5.0, 2.0)
    await pub.publicar_bandera(Bandera.ROJA, 2.0)

    cliente = ClienteFalso()
    await pub.conectar(cliente)

    estados = [e for e in cliente.enviados if e[0] == "granprix/carrera/estado"]
    assert len(estados) == 1 and estados[0][1]["fase"] == "roja"  # solo el último
    assert any(e[0] == "granprix/carrera/bandera" for e in cliente.enviados)


async def test_si_el_broker_cae_a_mitad_no_se_pierde_ni_se_lanza_error():
    pub = PublicadorMqtt()
    await pub.conectar(ClienteFalso(falla=True))
    await pub.publicar_bandera(Bandera.ROJA, 1.0)  # no lanza
    await pub.publicar_estado("T1", Fase.ROJA, [7], 0.0, 1.0)

    cliente = ClienteFalso()
    await pub.conectar(cliente)
    topicos = {e[0] for e in cliente.enviados}
    assert {"granprix/carrera/bandera", "granprix/carrera/estado"} <= topicos
