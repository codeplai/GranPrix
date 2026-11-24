import asyncio
import logging
from collections import deque
from collections.abc import Sequence

from pc_race.dominio.ranking import Posicion

log = logging.getLogger(__name__)


class TableroEnMemoria:
    """Guarda el último ranking y los avisos para el juez, y los escribe en el log.

    La ApiWeb lo lee y se suscribe para empujar los cambios por WebSocket.
    """

    def __init__(self, max_avisos: int = 100) -> None:
        self.tanda_id: str | None = None
        self.ranking: tuple[Posicion, ...] = ()
        self.avisos: deque[str] = deque(maxlen=max_avisos)
        self._suscriptores: set[asyncio.Queue[None]] = set()

    def suscribir(self) -> asyncio.Queue[None]:
        """Cola que recibe una señal en cada cambio. Hay que devolverla con `desuscribir`."""
        cola: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._suscriptores.add(cola)
        return cola

    def desuscribir(self, cola: asyncio.Queue[None]) -> None:
        self._suscriptores.discard(cola)

    def _notificar(self) -> None:
        for cola in self._suscriptores:
            if cola.empty():  # una señal pendiente basta: el lector arma un snapshot nuevo
                cola.put_nowait(None)

    async def publicar_ranking(self, tanda_id: str, ranking: Sequence[Posicion]) -> None:
        self.tanda_id = tanda_id
        self.ranking = tuple(ranking)
        self._notificar()

    async def avisar(self, mensaje: str) -> None:
        self.avisos.append(mensaje)
        log.warning("AVISO AL JUEZ: %s", mensaje)
        self._notificar()
