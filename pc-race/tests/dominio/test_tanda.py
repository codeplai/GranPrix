import pytest

from pc_race.dominio.errores import EquipoDesconocido, TransicionInvalida
from pc_race.dominio.intervencion import (
    Intervencion,
    MotivoExencion,
    Origen,
    TipoIntervencion,
)
from pc_race.dominio.pit import PoseDock
from pc_race.dominio.tanda import Fase, Tanda

POSE = PoseDock(dx=0.03, dy=0.04, dth=1.0)  # error lineal 0.05 m


def tanda_en_carrera(equipos=(7, 8), ts=1000.0):
    t = Tanda("T1", equipos)
    t.iniciar_carrera(ts)
    return t


def hacer_pit(t, equipo, estacion, ts, ok=True):
    t.registrar_solicitud(equipo, estacion, ts - 1, POSE, "A")
    return t.registrar_resultado(equipo, estacion, ts, ok, "B", 5.0)


def hacer_vuelta_valida(t, equipo, numero, t_inicio):
    for i, estacion in enumerate((1, 2, 3, 4)):
        hacer_pit(t, equipo, estacion, t_inicio + 10 * (i + 1))
    return t.cerrar_vuelta(equipo, numero, t_inicio, t_inicio + 50, (1, 2, 3, 4))


# ---------------------------------------------------------------- fases


def test_fases_normales():
    t = Tanda("T1", [7])
    assert t.fase is Fase.PENDIENTE
    t.iniciar_calentamiento(0)
    assert t.fase is Fase.CALENTAMIENTO
    t.iniciar_carrera(180)
    assert t.fase is Fase.CARRERA
    t.bandera_roja(200)
    assert t.fase is Fase.ROJA
    t.bandera_verde(230)
    assert t.fase is Fase.CARRERA
    t.terminar(300)
    assert t.fase is Fase.FIN


def test_puede_empezar_directo_en_carrera():
    t = Tanda("T1", [7])
    t.iniciar_carrera(0)
    assert t.fase is Fase.CARRERA


@pytest.mark.parametrize(
    "accion",
    ["bandera_roja", "bandera_verde", "terminar"],
)
def test_transiciones_invalidas_desde_pendiente(accion):
    t = Tanda("T1", [7])
    with pytest.raises(TransicionInvalida):
        getattr(t, accion)(0)


def test_no_se_sale_de_fin():
    t = tanda_en_carrera()
    t.terminar(1100)
    for accion in ("iniciar_carrera", "iniciar_calentamiento", "bandera_roja"):
        with pytest.raises(TransicionInvalida):
            getattr(t, accion)(1200)


# ---------------------------------------------------------------- reloj


def test_el_cronometro_de_carrera_se_detiene_en_bandera_roja():
    t = tanda_en_carrera(ts=1000)
    t.bandera_roja(1100)  # 100 s de carrera
    assert t.tiempo_carrera(1500) == 100  # roja: no avanza
    t.bandera_verde(1500)
    assert t.tiempo_carrera(1560) == 160


def test_carrera_agotada_a_los_12_minutos():
    t = tanda_en_carrera(ts=0)
    assert not t.carrera_agotada(719)
    assert t.carrera_agotada(720)


def test_calentamiento_agotado_a_los_3_minutos():
    t = Tanda("T1", [7])
    t.iniciar_calentamiento(0)
    assert not t.calentamiento_agotado(179)
    assert t.calentamiento_agotado(180)


# ------------------------------------------------------- intervenciones


def intervencion(equipo=7, ts=1010.0, declarada=True, origen=Origen.CARRITO, exencion=None):
    return Intervencion(equipo, TipoIntervencion.FISICA, ts, declarada, origen, exencion)


def test_intervencion_en_carrera_cuenta_uno():
    t = tanda_en_carrera()
    assert t.registrar_intervencion(intervencion()).puntos == 1


def test_intervencion_no_declarada_vista_por_el_juez_suma_tres_mas():
    t = tanda_en_carrera()
    registrada = t.registrar_intervencion(intervencion(declarada=False, origen=Origen.JUEZ))
    assert registrada.puntos == 4


def test_ajuste_antes_del_inicio_no_cuenta():
    t = Tanda("T1", [7])
    t.iniciar_calentamiento(0)
    registrada = t.registrar_intervencion(intervencion(ts=10))
    assert not registrada.cuenta
    assert registrada.exencion is MotivoExencion.AJUSTE_PREVIO


def test_intervencion_en_bandera_roja_no_cuenta():
    t = tanda_en_carrera()
    t.bandera_roja(1100)
    assert t.registrar_intervencion(intervencion(ts=1110)).exencion is MotivoExencion.BANDERA_ROJA


def test_intervencion_despues_del_fin_no_cuenta():
    t = tanda_en_carrera()
    t.terminar(1100)
    assert not t.registrar_intervencion(intervencion(ts=1110)).cuenta


@pytest.mark.parametrize(
    "motivo", [MotivoExencion.INICIAR, MotivoExencion.TABLERO, MotivoExencion.PAUSA_JUEZ]
)
def test_acciones_exentas_no_cuentan_ni_en_carrera(motivo):
    t = tanda_en_carrera()
    assert t.registrar_intervencion(intervencion(exencion=motivo)).puntos == 0


def test_intervencion_duplicada_no_se_cuenta_dos_veces():
    t = tanda_en_carrera()
    t.registrar_intervencion(intervencion())
    t.registrar_intervencion(intervencion())
    assert len(t.intervenciones(7)) == 1
    assert t.resumenes()[0].puntos_intervencion == 1


def test_equipo_desconocido():
    t = tanda_en_carrera()
    with pytest.raises(EquipoDesconocido):
        t.registrar_intervencion(intervencion(equipo=99))


# ------------------------------------------------------------ vueltas y pits


def test_vuelta_valida_se_guarda_y_entra_al_resumen():
    t = tanda_en_carrera()
    vuelta = hacer_vuelta_valida(t, 7, 1, 1000)
    assert vuelta is not None and vuelta.valida
    resumen = {r.equipo: r for r in t.resumenes()}[7]
    assert resumen.vueltas_validas == 1
    assert resumen.tiempo_medio_vuelta == 50
    assert resumen.error_pose_medio == pytest.approx(0.05)


def test_el_ultimo_pit_de_una_vuelta_no_invalida_la_siguiente():
    """Regresión: el pit 4 cae a medio segundo del límite entre vueltas, dentro de la
    tolerancia de reloj de la vuelta siguiente. Solo debe contar para la primera."""
    t = tanda_en_carrera(equipos=(7,), ts=1000)
    for estacion, ts in zip((1, 2, 3, 4), (1010, 1020, 1030, 1049.5), strict=True):
        hacer_pit(t, 7, estacion, ts)
    primera = t.cerrar_vuelta(7, 1, 1000, 1050)
    for estacion, ts in zip((1, 2, 3, 4), (1060, 1070, 1080, 1099.5), strict=True):
        hacer_pit(t, 7, estacion, ts)
    segunda = t.cerrar_vuelta(7, 2, 1050, 1100)

    assert primera.valida
    assert segunda.valida
    assert segunda.estaciones == (1, 2, 3, 4)


def test_vuelta_sin_pits_es_invalida_pero_se_guarda():
    t = tanda_en_carrera()
    vuelta = t.cerrar_vuelta(7, 1, 1000, 1050, (1, 2, 3, 4))
    assert vuelta is not None and not vuelta.valida
    assert t.resumenes()[0].vueltas_validas == 0


def test_vuelta_repetida_devuelve_la_primera():
    t = tanda_en_carrera()
    primera = hacer_vuelta_valida(t, 7, 1, 1000)
    repetida = t.cerrar_vuelta(7, 1, 1000, 1999, ())
    assert repetida == primera
    assert len(t.vueltas(7)) == 1


def test_en_calentamiento_no_cuentan_vueltas_ni_pits():
    t = Tanda("T1", [7])
    t.iniciar_calentamiento(0)
    assert hacer_pit(t, 7, 1, 10) is None
    assert t.cerrar_vuelta(7, 1, 0, 50, (1, 2, 3, 4)) is None


def test_equipo_termina_con_cuatro_vueltas_y_no_acepta_mas():
    t = tanda_en_carrera(equipos=(7,))
    for n in range(1, 5):
        hacer_vuelta_valida(t, 7, n, 1000 + 100 * n)
    assert t.equipo_termino(7) and t.todos_terminaron()
    assert t.cerrar_vuelta(7, 5, 2000, 2050, (1, 2, 3, 4)) is None


def test_todos_terminaron_exige_a_todos():
    t = tanda_en_carrera(equipos=(7, 8))
    for n in range(1, 5):
        hacer_vuelta_valida(t, 7, n, 1000 + 100 * n)
    assert not t.todos_terminaron()


def test_resultado_sin_solicitud_cuenta_pero_sin_pose():
    t = tanda_en_carrera()
    pit = t.registrar_resultado(7, 1, 1010, True, "B", 5.0)
    assert pit is not None and pit.pose is None
    assert t.resumenes()[0].error_pose_medio is None


def test_solicitud_y_resultado_duplicados_no_se_cuentan_dos_veces():
    t = tanda_en_carrera()
    hacer_pit(t, 7, 1, 1010)
    t.registrar_solicitud(7, 1, 1009, POSE, "A")  # duplicado de la solicitud ya usada
    t.registrar_resultado(7, 1, 1010, True, "B", 5.0)  # duplicado del resultado
    assert len(t.pits(7)) == 1
    # la solicitud duplicada no debe quedar pendiente para emparejarse con el próximo pit
    siguiente = t.registrar_resultado(7, 1, 1100, True, "B", 5.0)
    assert siguiente is not None and siguiente.pose is None


def test_pits_fallidos_no_entran_al_error_medio():
    t = tanda_en_carrera()
    hacer_pit(t, 7, 1, 1010, ok=False)
    assert t.resumenes()[0].error_pose_medio is None
