import pytest

from pc_race.aplicacion.casos_de_uso.calcular_ranking import CalcularRanking
from pc_race.aplicacion.casos_de_uso.cerrar_vuelta import CerrarVuelta
from pc_race.aplicacion.casos_de_uso.declarar_bandera import DeclararBandera
from pc_race.aplicacion.casos_de_uso.iniciar_tanda import IniciarTanda, TandaEnCurso
from pc_race.aplicacion.casos_de_uso.registrar_intervencion import RegistrarIntervencion
from pc_race.aplicacion.casos_de_uso.registrar_pit import RegistrarPit
from pc_race.aplicacion.casos_de_uso.vigilar_tiempos import VigilarTiempos
from pc_race.aplicacion.reconstruccion import reconstruir
from pc_race.aplicacion.sesion import SesionCarrera, SinTandaActiva
from pc_race.dominio.errores import EquipoDesconocido
from pc_race.dominio.intervencion import MotivoExencion, TipoIntervencion
from pc_race.dominio.pit import PoseDock
from pc_race.dominio.ranking import calcular_ranking
from pc_race.dominio.tanda import Fase

POSE = PoseDock(0.02, -0.01, 1.5)


async def vuelta_completa(sesion, equipo, numero, t0):
    pits, vueltas = RegistrarPit(sesion), CerrarVuelta(sesion)
    for i, estacion in enumerate((1, 2, 3, 4)):
        ts = t0 + 10 * (i + 1)
        await pits.solicitud(equipo, estacion, POSE, "A", ts - 2)
        await pits.resultado(equipo, estacion, True, "B", 5.0, ts)
    return await vueltas.ejecutar(equipo, numero, t0, t0 + 50, None, t0 + 50)


async def test_iniciar_tanda_publica_estado_turnos_y_bandera(sesion, publicador):
    await IniciarTanda(sesion).nueva([7, 8], con_calentamiento=False)
    assert publicador.estados[-1][1:] == ("carrera", (7, 8))
    assert publicador.banderas == ["verde"]
    assert (7, True) in publicador.turnos and (8, True) in publicador.turnos


async def test_no_se_puede_crear_otra_tanda_mientras_hay_una_en_curso(sesion, reloj):
    iniciar = IniciarTanda(sesion)
    await iniciar.nueva([7])
    with pytest.raises(TandaEnCurso):
        await iniciar.nueva([8])
    await iniciar.terminar()
    reloj.avanzar(1)  # el id de la tanda sale de la hora
    await iniciar.nueva([8])  # ya terminó la anterior


async def test_sin_tanda_los_casos_de_uso_fallan_con_error_claro(sesion):
    with pytest.raises(SinTandaActiva):
        await RegistrarIntervencion(sesion).desde_juez(7, TipoIntervencion.WEB)


async def test_la_bandera_roja_se_publica_y_la_intervencion_durante_ella_no_cuenta(
    sesion, publicador
):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    await DeclararBandera(sesion).roja()
    hecho = await RegistrarIntervencion(sesion).desde_carrito(
        7, TipoIntervencion.FISICA, True, 1_005.0
    )
    assert publicador.banderas[-1] == "roja"
    assert hecho is not None and hecho.puntos == 0
    await DeclararBandera(sesion).verde()
    assert sesion.tanda.fase is Fase.CARRERA


async def test_intervencion_del_juez_no_declarada_suma_cuatro(sesion):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    hecho = await RegistrarIntervencion(sesion).desde_juez(7, TipoIntervencion.WEB)
    assert hecho.puntos == 4
    assert CalcularRanking(sesion).calcular()[0].resumen.puntos_intervencion == 4


async def test_accion_exenta_del_juez_no_suma(sesion):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    hecho = await RegistrarIntervencion(sesion).desde_juez(
        7, TipoIntervencion.WEB, declarada=True, exencion=MotivoExencion.TABLERO
    )
    assert hecho.puntos == 0


async def test_equipo_que_no_esta_en_la_tanda(sesion):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    with pytest.raises(EquipoDesconocido):
        await RegistrarPit(sesion).solicitud(99, 1, POSE, "A", 1_001.0)


async def test_vuelta_valida_actualiza_el_ranking_del_tablero(sesion, tablero):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    vuelta = await vuelta_completa(sesion, 7, 1, 1_000.0)
    assert vuelta.valida
    assert tablero.rankings[-1][0].resumen.vueltas_validas == 1


async def test_la_tanda_termina_cuando_todos_completan_las_cuatro_vueltas(sesion, publicador):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    for n in range(1, 5):
        await vuelta_completa(sesion, 7, n, 1_000.0 + 100 * n)
    assert sesion.tanda.fase is Fase.FIN
    assert publicador.estados[-1][1] == "fin"
    assert (7, False) in publicador.turnos  # ya no está autorizado


async def test_la_tanda_termina_a_los_12_minutos(sesion, reloj, tablero):
    await IniciarTanda(sesion).nueva([7], con_calentamiento=False)
    vigilar = VigilarTiempos(sesion)
    reloj.avanzar(719)
    await vigilar.revisar()
    assert sesion.tanda.fase is Fase.CARRERA
    reloj.avanzar(1)
    await vigilar.revisar()
    assert sesion.tanda.fase is Fase.FIN
    assert any("tiempo de carrera" in a for a in tablero.avisos)


async def test_avisa_una_sola_vez_que_termino_el_calentamiento(sesion, reloj, tablero):
    await IniciarTanda(sesion).nueva([7])
    vigilar = VigilarTiempos(sesion)
    reloj.avanzar(181)
    await vigilar.revisar()
    await vigilar.revisar()
    assert len([a for a in tablero.avisos if "calentamiento" in a]) == 1
    assert sesion.tanda.fase is Fase.CALENTAMIENTO  # la carrera la inicia el juez


async def test_reinicio_reconstruye_la_tanda_desde_el_ledger(sesion, ledger):
    await IniciarTanda(sesion).nueva([7, 8], con_calentamiento=False)
    await vuelta_completa(sesion, 7, 1, 1_000.0)
    await RegistrarIntervencion(sesion).desde_juez(8, TipoIntervencion.FISICA)
    await DeclararBandera(sesion).roja()
    antes = sesion.ranking()

    tanda = reconstruir(sesion.tanda.id, await ledger.eventos(sesion.tanda.id))

    assert tanda.fase is Fase.ROJA
    assert tanda.tiempo_carrera(2_000.0) == sesion.tanda.tiempo_carrera(2_000.0)
    assert calcular_ranking(tanda.resumenes()) == antes


async def test_restaurar_y_republicar_tras_reiniciar(ledger, publicador, tablero, reloj):
    primera = SesionCarrera(ledger, publicador, tablero, reloj)
    await IniciarTanda(primera).nueva([7], con_calentamiento=False)
    await DeclararBandera(primera).roja()

    publicador2, tablero2 = type(publicador)(), type(tablero)()
    segunda = SesionCarrera(ledger, publicador2, tablero2, reloj)
    assert await segunda.restaurar()
    await segunda.republicar()

    assert segunda.tanda.fase is Fase.ROJA
    assert publicador2.estados[-1][1] == "roja"
    assert publicador2.banderas == ["roja"]
    assert tablero2.rankings  # volvió a publicar el ranking


async def test_restaurar_sin_ledger_previo_no_hace_nada(sesion):
    assert not await sesion.restaurar()
