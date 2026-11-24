from pc_race.aplicacion.sesion import SesionCarrera


class VigilarTiempos:
    """Se llama cada segundo. Termina la tanda a los 12 min de carrera y avisa al juez
    cuando acaba el calentamiento (la carrera la inicia el juez)."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion
        self._calentamiento_avisado: str | None = None

    async def revisar(self) -> None:
        tanda = self._sesion.tanda
        if tanda is None:
            return
        ts = self._sesion.reloj.ahora()
        if tanda.carrera_agotada(ts):
            await self._sesion.tablero.avisar(f"Tanda {tanda.id}: se acabó el tiempo de carrera")
            await self._sesion.cambiar_fase("fin")
        elif tanda.calentamiento_agotado(ts) and self._calentamiento_avisado != tanda.id:
            self._calentamiento_avisado = tanda.id
            await self._sesion.tablero.avisar(
                f"Tanda {tanda.id}: terminó el calentamiento, falta iniciar la carrera"
            )
