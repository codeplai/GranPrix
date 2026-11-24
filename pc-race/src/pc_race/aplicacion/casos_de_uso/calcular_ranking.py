from collections.abc import Sequence

from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.ranking import Posicion


class CalcularRanking:
    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    def calcular(self) -> Sequence[Posicion]:
        return self._sesion.ranking()

    async def publicar(self) -> None:
        await self._sesion.publicar_ranking()
