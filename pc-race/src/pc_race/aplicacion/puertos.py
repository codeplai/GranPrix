"""Interfaces que usa la aplicación. Los adaptadores las implementan."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pc_race.dominio.bandera import Bandera
from pc_race.dominio.ranking import Posicion
from pc_race.dominio.tanda import Fase


class Reloj(Protocol):
    def ahora(self) -> float:
        """Segundos Unix (NTP sincronizado por el sistema operativo)."""
        ...


@dataclass(frozen=True)
class EventoLedger:
    """Un hecho de la tanda. El ledger guarda estos eventos y de ellos se reconstruye la tanda.

    `clave` evita guardar dos veces el mismo hecho (QoS 1 puede duplicar mensajes).
    """

    tanda_id: str
    ts: float
    tipo: str
    datos: dict[str, Any] = field(default_factory=dict)
    clave: str | None = None


class Ledger(Protocol):
    """Registro durable de la carrera (en `01-pc-race.md` figura como RepositorioIntervenciones,
    pero guarda todos los eventos para poder reconstruir la tanda tras un reinicio)."""

    async def agregar(self, evento: EventoLedger) -> bool:
        """Guarda el evento. False si ya existía uno con la misma clave."""
        ...

    async def eventos(self, tanda_id: str) -> list[EventoLedger]: ...

    async def ultima_tanda(self) -> str | None: ...


class PublicadorEstado(Protocol):
    """Lo que Race Control le dice a carritos y estaciones."""

    async def publicar_estado(
        self, tanda_id: str, fase: Fase, equipos: Sequence[int], t_carrera: float, ts: float
    ) -> None: ...

    async def publicar_bandera(self, bandera: Bandera, ts: float) -> None: ...

    async def publicar_turno_carrito(
        self, equipo: int, autorizado: bool, tanda_id: str | None, ts: float
    ) -> None: ...


class PublicadorTablero(Protocol):
    """Lo que Race Control le muestra al juez y al público."""

    async def publicar_ranking(self, tanda_id: str, ranking: Sequence[Posicion]) -> None: ...

    async def avisar(self, mensaje: str) -> None: ...
