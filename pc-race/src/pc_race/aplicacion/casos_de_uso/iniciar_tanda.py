from collections.abc import Sequence

from pc_race.aplicacion.puertos import EventoLedger
from pc_race.aplicacion.reconstruccion import TANDA_CREADA
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.errores import ErrorDominio, TransicionInvalida
from pc_race.dominio.tanda import Fase, Tanda


class TandaEnCurso(ErrorDominio):
    """Ya hay una tanda sin terminar."""


class IniciarTanda:
    """Crea la tanda y la lleva a calentamiento o a carrera; también pasa a carrera y termina."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    async def nueva(self, equipos: Sequence[int], con_calentamiento: bool = True) -> str:
        sesion = self._sesion
        if not equipos:
            raise ErrorDominio("una tanda necesita al menos un equipo")
        if sesion.tanda is not None and sesion.tanda.fase is not Fase.FIN:
            raise TandaEnCurso(f"la tanda {sesion.tanda.id} sigue en fase {sesion.tanda.fase}")

        ts = sesion.reloj.ahora()
        tanda = Tanda(f"T{int(ts)}", equipos, sesion.reglas)
        await sesion.ledger.agregar(
            EventoLedger(tanda.id, ts, TANDA_CREADA, {"equipos": list(tanda.equipos)})
        )
        sesion.tanda = tanda
        await sesion.cambiar_fase("calentamiento" if con_calentamiento else "carrera")
        return tanda.id

    async def pasar_a_carrera(self) -> None:
        await self._sesion.cambiar_fase("carrera")

    async def terminar(self) -> None:
        if self._sesion.tanda_activa().fase is Fase.PENDIENTE:
            raise TransicionInvalida("la tanda no ha empezado")
        await self._sesion.cambiar_fase("fin")
