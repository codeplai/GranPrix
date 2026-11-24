import logging
from typing import Any, Protocol

from pydantic import ValidationError

from contrato import modelos
from contrato.topicos import SUSCRIPCIONES, Ruta, interpretar
from pc_race.aplicacion.casos_de_uso.cerrar_vuelta import CerrarVuelta
from pc_race.aplicacion.casos_de_uso.registrar_intervencion import RegistrarIntervencion
from pc_race.aplicacion.casos_de_uso.registrar_pit import RegistrarPit
from pc_race.aplicacion.metricas import Metricas
from pc_race.aplicacion.monitor_latidos import MonitorLatidos
from pc_race.aplicacion.puertos import Reloj
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.errores import ErrorDominio
from pc_race.dominio.intervencion import TipoIntervencion
from pc_race.dominio.pit import PoseDock

log = logging.getLogger(__name__)


class _ClienteEscucha(Protocol):
    @property
    def messages(self) -> Any: ...

    async def subscribe(self, topic: str, qos: int = 0) -> Any: ...


class MqttGateway:
    """Convierte mensajes MQTT en llamadas a los casos de uso.

    Un mensaje inválido se descarta y se cuenta; nunca detiene a Race Control.
    `procesar` no necesita broker, así que se prueba con mensajes en bruto.
    """

    def __init__(
        self,
        sesion: SesionCarrera,
        metricas: Metricas,
        monitor: MonitorLatidos,
        reloj: Reloj,
    ) -> None:
        self._metricas = metricas
        self._monitor = monitor
        self._reloj = reloj
        self._pits = RegistrarPit(sesion)
        self._intervenciones = RegistrarIntervencion(sesion)
        self._vueltas = CerrarVuelta(sesion)

    async def escuchar(self, cliente: _ClienteEscucha) -> None:
        for suscripcion in SUSCRIPCIONES:
            await cliente.subscribe(suscripcion, qos=1)
        async for mensaje in cliente.messages:
            payload = mensaje.payload
            await self.procesar(str(mensaje.topic), payload if payload is not None else b"")

    async def procesar(self, topico: str, payload: bytes | str) -> None:
        self._metricas.contar_recibido()
        ruta = interpretar(topico)
        if ruta is None:
            self._metricas.contar_invalido(topico)
            return
        canal = f"{ruta.origen}/{ruta.canal}"
        try:
            await self._despachar(ruta, payload)
        except (ValidationError, ValueError) as error:
            self._metricas.contar_invalido(canal)
            log.warning("mensaje inválido en %s: %s", topico, error)
        except ErrorDominio as error:
            self._metricas.contar_descartado(type(error).__name__)
            log.info("mensaje descartado en %s: %s", topico, error)
        except Exception:
            self._metricas.contar_descartado("error_interno")
            log.exception("error inesperado procesando %s", topico)

    async def _despachar(self, ruta: Ruta, payload: bytes | str) -> None:
        ahora = self._reloj.ahora()
        clave = f"{ruta.origen}:{ruta.numero}"

        if ruta.origen == "estacion":
            if ruta.canal == "estado":
                estado = _leer_estado(payload, ahora)
                if estado.estado is modelos.EstadoEstacion.OFFLINE:
                    await self._monitor.caida(clave, ahora)
                else:
                    await self._monitor.latido(clave, ahora)
            elif ruta.canal == "solicitud":
                solicitud = modelos.SolicitudMsg.model_validate_json(payload)
                _exigir(solicitud.dock == ruta.numero, "dock no coincide con el tópico")
                p = solicitud.pose
                await self._pits.solicitud(
                    solicitud.equipo,
                    ruta.numero,
                    PoseDock(p.dx, p.dy, p.dth),
                    solicitud.pieza_trae,
                    solicitud.ts,
                )
            else:  # resultado
                resultado = modelos.ResultadoMsg.model_validate_json(payload)
                await self._pits.resultado(
                    resultado.equipo,
                    ruta.numero,
                    resultado.ok,
                    resultado.pieza_dejo,
                    resultado.t_cambio,
                    resultado.ts,
                )
            return

        # carrito
        if ruta.canal == "telemetria":
            telemetria = modelos.TelemetriaMsg.model_validate_json(payload)
            _exigir(telemetria.equipo == ruta.numero, "equipo no coincide con el tópico")
            await self._monitor.latido(clave, ahora)
        elif ruta.canal == "evento":
            evento = modelos.EventoMsg.model_validate_json(payload)
            _exigir(evento.equipo == ruta.numero, "equipo no coincide con el tópico")
            await self._monitor.latido(clave, ahora)
            if evento.tipo == "intervencion" and evento.subtipo is not None:
                await self._intervenciones.desde_carrito(
                    evento.equipo, TipoIntervencion(evento.subtipo), evento.declarada, evento.ts
                )
            # pit_ok y reintento son informativos: el pit lo cierra el `resultado` de la estación
        else:  # vuelta
            vuelta = modelos.VueltaMsg.model_validate_json(payload)
            _exigir(vuelta.equipo == ruta.numero, "equipo no coincide con el tópico")
            await self._monitor.latido(clave, ahora)
            await self._vueltas.ejecutar(
                vuelta.equipo,
                vuelta.numero,
                vuelta.t_inicio,
                vuelta.t_fin,
                vuelta.estaciones,
                vuelta.ts,
            )


def _exigir(condicion: bool, motivo: str) -> None:
    if not condicion:
        raise ValueError(motivo)


def _leer_estado(payload: bytes | str, ahora: float) -> modelos.EstadoEstacionMsg:
    """El estado normal es JSON; el Last Will puede llegar como texto plano ("OFFLINE")."""
    texto = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    simple = texto.strip().strip('"')
    if simple in {e.value for e in modelos.EstadoEstacion}:
        return modelos.EstadoEstacionMsg(ts=ahora, estado=modelos.EstadoEstacion(simple))
    return modelos.EstadoEstacionMsg.model_validate_json(texto)
