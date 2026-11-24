"""Aplica eventos del ledger a una Tanda, en vivo o al reconstruir tras un reinicio."""

import logging
from collections.abc import Iterable
from typing import Any

from pc_race.aplicacion.puertos import EventoLedger
from pc_race.dominio.errores import ErrorDominio
from pc_race.dominio.intervencion import Intervencion, MotivoExencion, Origen, TipoIntervencion
from pc_race.dominio.pit import PoseDock
from pc_race.dominio.tanda import ReglasTanda, Tanda

log = logging.getLogger(__name__)

TANDA_CREADA = "tanda_creada"
FASE = "fase"
INTERVENCION = "intervencion"
SOLICITUD = "solicitud"
RESULTADO = "resultado"
VUELTA = "vuelta"

ACCIONES_FASE = ("calentamiento", "carrera", "roja", "verde", "fin")


def aplicar_evento(tanda: Tanda, evento: EventoLedger) -> Any:
    """Aplica el evento a la tanda. Devuelve el efecto en el dominio, o None si no contó."""
    d = evento.datos
    match evento.tipo:
        case "fase":
            accion = d["accion"]
            if accion == "calentamiento":
                tanda.iniciar_calentamiento(evento.ts)
            elif accion == "carrera":
                tanda.iniciar_carrera(evento.ts)
            elif accion == "roja":
                tanda.bandera_roja(evento.ts)
            elif accion == "verde":
                tanda.bandera_verde(evento.ts)
            elif accion == "fin":
                tanda.terminar(evento.ts)
            else:
                raise ErrorDominio(f"acción de fase desconocida: {accion!r}")
            return None
        case "intervencion":
            exencion = d.get("exencion")
            return tanda.registrar_intervencion(
                Intervencion(
                    equipo=d["equipo"],
                    tipo=TipoIntervencion(d["tipo"]),
                    ts=evento.ts,
                    declarada=d["declarada"],
                    origen=Origen(d["origen"]),
                    exencion=MotivoExencion(exencion) if exencion else None,
                )
            )
        case "solicitud":
            conto = tanda.registrar_solicitud(
                d["equipo"],
                d["estacion"],
                evento.ts,
                PoseDock(d["dx"], d["dy"], d["dth"]),
                d.get("pieza_trae"),
            )
            return True if conto else None
        case "resultado":
            return tanda.registrar_resultado(
                d["equipo"],
                d["estacion"],
                evento.ts,
                d["ok"],
                d.get("pieza_dejo"),
                d.get("t_cambio"),
            )
        case "vuelta":
            return tanda.cerrar_vuelta(
                d["equipo"], d["numero"], d["t_inicio"], d["t_fin"], d.get("estaciones")
            )
        case otro:
            raise ErrorDominio(f"tipo de evento desconocido: {otro!r}")


def reconstruir(
    tanda_id: str, eventos: Iterable[EventoLedger], reglas: ReglasTanda | None = None
) -> Tanda | None:
    """Rehace la tanda repitiendo sus eventos en orden. None si el ledger no tiene la tanda.

    Un evento que ya no se puede aplicar se salta con una advertencia: un dato malo no debe
    impedir que Race Control arranque.
    """
    tanda: Tanda | None = None
    for evento in eventos:
        if evento.tipo == TANDA_CREADA:
            tanda = Tanda(tanda_id, evento.datos["equipos"], reglas)
            continue
        if tanda is None:
            continue
        try:
            aplicar_evento(tanda, evento)
        except (ErrorDominio, KeyError, ValueError) as error:
            log.warning("evento %s saltado al reconstruir %s: %s", evento.tipo, tanda_id, error)
    return tanda
