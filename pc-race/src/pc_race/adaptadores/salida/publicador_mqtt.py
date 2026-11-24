import logging
from collections import deque
from collections.abc import Sequence
from typing import Protocol

import aiomqtt
from pydantic import BaseModel

from contrato import modelos, topicos
from pc_race.dominio.bandera import Bandera
from pc_race.dominio.tanda import Fase

log = logging.getLogger(__name__)


class _ClienteMqtt(Protocol):
    async def publish(
        self, topic: str, payload: bytes | str, qos: int = 0, retain: bool = False
    ) -> None: ...


class PublicadorMqtt:
    """Publica el estado de la carrera. Si el broker está caído no pierde nada:
    los mensajes retenidos se guardan (solo importa el último por tópico) y los demás
    esperan en una cola corta; todo sale al reconectar."""

    def __init__(self, max_pendientes: int = 200) -> None:
        self._cliente: _ClienteMqtt | None = None
        self._retenidos: dict[str, tuple[bytes, int]] = {}
        self._pendientes: deque[tuple[str, bytes, int]] = deque(maxlen=max_pendientes)

    async def conectar(self, cliente: _ClienteMqtt) -> None:
        self._cliente = cliente
        for topico, (payload, qos) in list(self._retenidos.items()):
            await self._enviar(topico, payload, qos, retain=True)
        while self._pendientes and self._cliente is not None:
            topico, payload, qos = self._pendientes.popleft()
            await self._enviar(topico, payload, qos, retain=False)

    def desconectar(self) -> None:
        self._cliente = None

    async def publicar_estado(
        self, tanda_id: str, fase: Fase, equipos: Sequence[int], t_carrera: float, ts: float
    ) -> None:
        mensaje = modelos.EstadoCarreraMsg(
            ts=ts,
            tanda=tanda_id,
            fase=modelos.FaseMsg(fase.value),
            equipos=list(equipos),
            t_carrera=t_carrera,
        )
        await self._publicar(topicos.topico_estado_carrera(), mensaje, qos=1, retain=True)

    async def publicar_bandera(self, bandera: Bandera, ts: float) -> None:
        mensaje = modelos.BanderaMsg(ts=ts, bandera=bandera.value)
        await self._publicar(topicos.topico_bandera(), mensaje, qos=1, retain=False)

    async def publicar_turno_carrito(
        self, equipo: int, autorizado: bool, tanda_id: str | None, ts: float
    ) -> None:
        mensaje = modelos.TurnoCarritoMsg(ts=ts, autorizado=autorizado, tanda=tanda_id)
        await self._publicar(topicos.topico_turno_carrito(equipo), mensaje, qos=1, retain=True)

    async def _publicar(self, topico: str, mensaje: BaseModel, qos: int, retain: bool) -> None:
        payload = mensaje.model_dump_json().encode()
        if retain:
            self._retenidos[topico] = (payload, qos)
        if self._cliente is None:
            if not retain:
                self._pendientes.append((topico, payload, qos))
            return
        await self._enviar(topico, payload, qos, retain)

    async def _enviar(self, topico: str, payload: bytes, qos: int, retain: bool) -> None:
        if self._cliente is None:
            return
        try:
            await self._cliente.publish(topico, payload, qos=qos, retain=retain)
        except aiomqtt.MqttError as error:
            log.warning("no se pudo publicar en %s: %s", topico, error)
            self._cliente = None
            if not retain:
                self._pendientes.append((topico, payload, qos))
