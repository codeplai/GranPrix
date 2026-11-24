"""Arma todo y arranca Race Control."""

import asyncio
import logging
import sys

import aiomqtt
import uvicorn

from pc_race.adaptadores.entrada.api_web import crear_app
from pc_race.adaptadores.entrada.consola_juez import ConsolaJuez
from pc_race.adaptadores.entrada.mqtt_gateway import MqttGateway
from pc_race.adaptadores.salida.ledger_sqlite import LedgerSqlite
from pc_race.adaptadores.salida.publicador_mqtt import PublicadorMqtt
from pc_race.adaptadores.salida.reloj import RelojSistema
from pc_race.adaptadores.salida.tablero_memoria import TableroEnMemoria
from pc_race.aplicacion.casos_de_uso.vigilar_tiempos import VigilarTiempos
from pc_race.aplicacion.metricas import Metricas
from pc_race.aplicacion.monitor_latidos import MonitorLatidos
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.configuracion import Configuracion

log = logging.getLogger("pc_race")

ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 30.0


async def _vigilar(
    vigilar_tiempos: VigilarTiempos, monitor: MonitorLatidos, reloj: RelojSistema
) -> None:
    while True:
        await vigilar_tiempos.revisar()
        await monitor.revisar(reloj.ahora())
        await asyncio.sleep(1.0)


async def servir(config: Configuracion) -> None:
    reloj = RelojSistema()
    ledger = LedgerSqlite(config.ledger)
    await ledger.abrir()
    publicador = PublicadorMqtt()
    tablero = TableroEnMemoria()
    sesion = SesionCarrera(ledger, publicador, tablero, reloj)
    metricas = Metricas()
    monitor = MonitorLatidos(tablero)
    gateway = MqttGateway(sesion, metricas, monitor, reloj)

    if await sesion.restaurar():
        log.info("reiniciado: tanda restaurada desde el ledger")

    tareas = [asyncio.create_task(_vigilar(VigilarTiempos(sesion), monitor, reloj))]

    app = crear_app(sesion, tablero, metricas, monitor, config.api_token)
    servidor = uvicorn.Server(
        uvicorn.Config(app, host=config.api_host, port=config.api_port, log_level="warning")
    )
    tareas.append(asyncio.create_task(servidor.serve()))
    log.info("tablero del juez en http://%s:%s", config.api_host, config.api_port)
    if config.api_host not in ("127.0.0.1", "localhost") and not config.api_token:
        log.warning("la API escucha en la red sin GRANPRIX_API_TOKEN: cualquiera puede dar órdenes")

    if config.consola:
        consola = asyncio.create_task(ConsolaJuez(sesion).leer())
        consola.add_done_callback(lambda _: log.info("consola del juez cerrada"))
        tareas.append(consola)

    espera = ESPERA_INICIAL
    try:
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=config.mqtt_host,
                    port=config.mqtt_port,
                    username=config.mqtt_usuario,
                    password=config.mqtt_clave,
                    identifier="racecontrol",
                ) as cliente:
                    log.info("conectado al broker %s:%s", config.mqtt_host, config.mqtt_port)
                    espera = ESPERA_INICIAL
                    await publicador.conectar(cliente)
                    await sesion.republicar()
                    await gateway.escuchar(cliente)
            except aiomqtt.MqttError as error:
                publicador.desconectar()
                log.warning("broker no disponible (%s); reintento en %.0f s", error, espera)
                await asyncio.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA)
    finally:
        servidor.should_exit = True
        for tarea in tareas:
            tarea.cancel()
        await ledger.cerrar()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("transitions").setLevel(logging.WARNING)  # un INFO por cada transición
    config = Configuracion.desde_entorno()
    # En Windows aiomqtt necesita el bucle Selector (el Proactor no tiene add_reader).
    factoria = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(servir(config), loop_factory=factoria)
    except KeyboardInterrupt:
        log.info("detenido")


if __name__ == "__main__":
    run()
