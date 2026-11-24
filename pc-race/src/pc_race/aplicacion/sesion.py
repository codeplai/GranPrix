"""La carrera en curso: la tanda activa y los puertos que los casos de uso comparten."""

import logging
from typing import Any

from pc_race.aplicacion.puertos import (
    EventoLedger,
    Ledger,
    PublicadorEstado,
    PublicadorTablero,
    Reloj,
)
from pc_race.aplicacion.reconstruccion import FASE, aplicar_evento, reconstruir
from pc_race.dominio.bandera import Bandera
from pc_race.dominio.errores import EquipoDesconocido, ErrorDominio
from pc_race.dominio.ranking import Posicion, calcular_ranking
from pc_race.dominio.tanda import Fase, ReglasTanda, Tanda

log = logging.getLogger(__name__)

_BANDERA_POR_ACCION = {"carrera": Bandera.VERDE, "verde": Bandera.VERDE, "roja": Bandera.ROJA}
_FASES_AUTORIZADAS = (Fase.CALENTAMIENTO, Fase.CARRERA, Fase.ROJA)


class SinTandaActiva(ErrorDominio):
    """Llegó un mensaje que necesita una tanda y no hay ninguna."""


class SesionCarrera:
    def __init__(
        self,
        ledger: Ledger,
        estado: PublicadorEstado,
        tablero: PublicadorTablero,
        reloj: Reloj,
        reglas: ReglasTanda | None = None,
    ) -> None:
        self.ledger = ledger
        self.estado = estado
        self.tablero = tablero
        self.reloj = reloj
        self.reglas = reglas or ReglasTanda()
        self.tanda: Tanda | None = None

    def tanda_activa(self) -> Tanda:
        if self.tanda is None:
            raise SinTandaActiva("no hay una tanda creada")
        return self.tanda

    async def registrar(
        self, tipo: str, datos: dict[str, Any], ts: float, clave: str | None = None
    ) -> Any:
        """Aplica el hecho a la tanda y, si contó, lo guarda en el ledger.

        Primero el dominio: así un hecho inválido nunca llega al ledger.
        Devuelve el efecto en el dominio, o None si el hecho no contó.
        """
        tanda = self.tanda_activa()
        equipo = datos.get("equipo")
        if equipo is not None and equipo not in tanda.equipos:
            raise EquipoDesconocido(f"el equipo {equipo} no está en la tanda {tanda.id}")

        evento = EventoLedger(tanda.id, ts, tipo, datos, clave)
        efecto = aplicar_evento(tanda, evento)
        if efecto is not None or tipo == FASE:
            await self.ledger.agregar(evento)
        return efecto

    async def cambiar_fase(self, accion: str) -> None:
        """calentamiento | carrera | roja | verde | fin: lo aplica, lo guarda y lo publica."""
        ts = self.reloj.ahora()
        await self.registrar(FASE, {"accion": accion}, ts)
        await self.publicar_estado()
        if bandera := _BANDERA_POR_ACCION.get(accion):
            await self.estado.publicar_bandera(bandera, ts)
        await self.publicar_ranking()  # también avisa al tablero de que cambió la fase

    async def publicar_estado(self) -> None:
        tanda = self.tanda
        if tanda is None:
            return
        ts = self.reloj.ahora()
        await self.estado.publicar_estado(
            tanda.id, tanda.fase, tanda.equipos, tanda.tiempo_carrera(ts), ts
        )
        autorizado = tanda.fase in _FASES_AUTORIZADAS
        for equipo in tanda.equipos:
            await self.estado.publicar_turno_carrito(equipo, autorizado, tanda.id, ts)

    def ranking(self) -> tuple[Posicion, ...]:
        tanda = self.tanda_activa()
        return calcular_ranking(tanda.resumenes(), tanda.reglas.min_vueltas_validas)

    async def publicar_ranking(self) -> None:
        if self.tanda is not None:
            await self.tablero.publicar_ranking(self.tanda.id, self.ranking())

    async def restaurar(self) -> bool:
        """Tras un reinicio: rehace la última tanda desde el ledger."""
        tanda_id = await self.ledger.ultima_tanda()
        if tanda_id is None:
            return False
        tanda = reconstruir(tanda_id, await self.ledger.eventos(tanda_id), self.reglas)
        if tanda is None:
            return False
        self.tanda = tanda
        log.info("tanda %s restaurada en fase %s", tanda.id, tanda.fase)
        return True

    async def republicar(self) -> None:
        """Vuelve a publicar lo retenido: tras un reinicio o al reconectar con el broker."""
        if self.tanda is None:
            return
        await self.publicar_estado()
        ts = self.reloj.ahora()
        if self.tanda.fase is Fase.ROJA:
            await self.estado.publicar_bandera(Bandera.ROJA, ts)
        elif self.tanda.fase is Fase.CARRERA:
            await self.estado.publicar_bandera(Bandera.VERDE, ts)
        await self.publicar_ranking()
