import pytest

from pc_race.dominio.errores import VueltaInvalida
from pc_race.dominio.pit import Pit
from pc_race.dominio.vuelta import evaluar_vuelta

ORDEN = (1, 2, 3, 4)


def pit(estacion, ts, ok=True, equipo=7):
    return Pit(equipo=equipo, estacion=estacion, ts_resultado=ts, ok=ok)


def pits_completos(equipo=7):
    return [
        pit(1, 110, equipo=equipo),
        pit(2, 120, equipo=equipo),
        pit(3, 130, equipo=equipo),
        pit(4, 140, equipo=equipo),
    ]


def evaluar(estaciones=ORDEN, pits=None, t_inicio=100.0, t_fin=150.0):
    return evaluar_vuelta(
        equipo=7,
        numero=1,
        t_inicio=t_inicio,
        t_fin=t_fin,
        estaciones=estaciones,
        pits=pits_completos() if pits is None else pits,
        orden=ORDEN,
        tolerancia=1.0,
    )


def test_vuelta_en_orden_con_cuatro_pits_ok_es_valida():
    assert evaluar().valida


def test_estaciones_fuera_de_orden_no_es_valida():
    assert not evaluar(estaciones=(1, 3, 2, 4)).valida


def test_estacion_saltada_no_es_valida():
    assert not evaluar(estaciones=(1, 2, 4)).valida


def test_pit_con_resultado_no_ok_invalida_la_vuelta():
    pits = pits_completos()
    pits[2] = pit(3, 130, ok=False)
    assert not evaluar(pits=pits).valida


def test_reintento_ok_despues_de_un_fallo_deja_la_vuelta_valida():
    pits = pits_completos() + [pit(3, 138, ok=False)]
    pits[2] = pit(3, 130, ok=False)
    pits.append(pit(3, 145, ok=True))
    assert evaluar(pits=pits, t_fin=150).valida


def test_falta_el_resultado_de_una_estacion():
    assert not evaluar(pits=pits_completos()[:3]).valida


def test_pit_de_otra_vuelta_no_cuenta():
    pits = pits_completos()
    pits[0] = pit(1, 50)  # mucho antes de la ventana
    assert not evaluar(pits=pits).valida


def test_tolerancia_de_reloj_en_los_bordes():
    pits = pits_completos()
    pits[0] = pit(1, 99.5)  # medio segundo antes: dentro de la tolerancia de 1 s
    assert evaluar(pits=pits).valida


def test_pit_de_otro_equipo_no_cuenta():
    pits = pits_completos(equipo=8)
    assert not evaluar(pits=pits).valida


def test_sin_estaciones_informadas_se_infiere_el_recorrido_de_los_pits():
    assert evaluar(estaciones=None).valida


def test_recorrido_inferido_fuera_de_orden_no_es_valido():
    pits = [pit(1, 110), pit(3, 120), pit(2, 130), pit(4, 140)]
    assert not evaluar(estaciones=None, pits=pits).valida


def test_recorrido_inferido_ignora_fallos_y_repeticiones():
    pits = pits_completos() + [pit(2, 125, ok=False), pit(2, 126)]
    assert evaluar(estaciones=None, pits=pits).valida


def test_vuelta_que_termina_antes_de_empezar_es_un_error():
    with pytest.raises(VueltaInvalida):
        evaluar(t_inicio=150, t_fin=100)


def test_duracion():
    assert evaluar().duracion == 50.0
