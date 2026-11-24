from collections.abc import Sequence

from pc_race.aplicacion.reconstruccion import VUELTA
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.tanda import Fase
from pc_race.dominio.vuelta import Vuelta


class CerrarVuelta:
    """Valida la vuelta contra los resultados de las estaciones. Si con ella todos los equipos
    completan sus vueltas, la tanda termina."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    async def ejecutar(
        self,
        equipo: int,
        numero: int,
        t_inicio: float,
        t_fin: float,
        estaciones: Sequence[int] | None,
        ts: float,
    ) -> Vuelta | None:
        datos = {
            "equipo": equipo,
            "numero": numero,
            "t_inicio": t_inicio,
            "t_fin": t_fin,
            "estaciones": list(estaciones) if estaciones is not None else None,
        }
        vuelta: Vuelta | None = await self._sesion.registrar(
            VUELTA, datos, ts, f"vuelta:{equipo}:{numero}"
        )
        if vuelta is None:
            return None

        await self._sesion.publicar_ranking()
        tanda = self._sesion.tanda_activa()
        if tanda.fase is Fase.CARRERA and tanda.todos_terminaron():
            await self._sesion.cambiar_fase("fin")
        return vuelta
