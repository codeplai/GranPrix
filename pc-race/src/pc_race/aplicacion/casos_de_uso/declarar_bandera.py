from pc_race.aplicacion.sesion import SesionCarrera


class DeclararBandera:
    """Bandera roja o verde. Lo que ocurre durante la roja no cuenta como intervención
    (lo decide la Tanda según su fase) y el cronómetro de carrera se detiene."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    async def roja(self) -> None:
        await self._sesion.cambiar_fase("roja")

    async def verde(self) -> None:
        await self._sesion.cambiar_fase("verde")
