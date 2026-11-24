"""Modelos pydantic de los mensajes (ver docs/arquitectura/00-contrato-mqtt.md).

Reglas de compatibilidad:
- Un campo nuevo se agrega como opcional y no sube `v`; por eso `extra="ignore"`.
- Si cambia el significado de un campo, sube `v` y se agrega a VERSIONES_ACEPTADAS.

Unidades: metros para dx y dy, grados para dth, segundos para tiempos.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

VERSION_ACTUAL = 1
VERSIONES_ACEPTADAS = frozenset({1})


class Mensaje(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    v: int = VERSION_ACTUAL
    ts: float

    @field_validator("v")
    @classmethod
    def _version_conocida(cls, v: int) -> int:
        if v not in VERSIONES_ACEPTADAS:
            raise ValueError(f"versión {v} no soportada (aceptadas: {sorted(VERSIONES_ACEPTADAS)})")
        return v


# ------------------------------------------------------------- Race Control → todos


class FaseMsg(StrEnum):
    PENDIENTE = "pendiente"
    CALENTAMIENTO = "calentamiento"
    CARRERA = "carrera"
    ROJA = "roja"
    FIN = "fin"


class EstadoCarreraMsg(Mensaje):
    """granprix/carrera/estado (QoS 1, retenido)."""

    tanda: str
    fase: FaseMsg
    equipos: list[int]
    t_carrera: float = 0.0


class BanderaMsg(Mensaje):
    """granprix/carrera/bandera (QoS 1)."""

    bandera: Literal["verde", "roja"]


class TurnoCarritoMsg(Mensaje):
    """granprix/eqNN/turno (QoS 1, retenido)."""

    autorizado: bool
    tanda: str | None = None


class TurnoEstacionMsg(Mensaje):
    """granprix/estacion/<n>/turno (QoS 1, retenido). `equipo` es None si nadie tiene turno."""

    equipo: int | None = None


# ------------------------------------------------------------------- estación


class EstadoEstacion(StrEnum):
    LIBRE = "LIBRE"
    ESPERANDO = "ESPERANDO"
    CAMBIANDO = "CAMBIANDO"
    LISTA = "LISTA"
    OFFLINE = "OFFLINE"


class EstadoEstacionMsg(Mensaje):
    """granprix/estacion/<n>/estado (QoS 1, retenido). También lo publica el Last Will."""

    estado: EstadoEstacion


class ResultadoMsg(Mensaje):
    """granprix/estacion/<n>/resultado (QoS 1)."""

    equipo: int
    ok: bool
    pieza_dejo: str | None = None
    t_cambio: float | None = None


# -------------------------------------------------------------------- carrito


class PoseMsg(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    dx: float
    dy: float
    dth: float


class SolicitudMsg(Mensaje):
    """granprix/estacion/<n>/solicitud (QoS 1)."""

    equipo: int
    dock: int
    pose: PoseMsg
    pieza_trae: str | None = None


class TelemetriaMsg(Mensaje):
    """granprix/eqNN/telemetria (QoS 0, hasta 5 Hz). El contenido de `pose` no está fijado."""

    equipo: int
    pose: dict[str, float] | None = None
    bateria: float | None = None
    velocidad: float | None = None


class EventoMsg(Mensaje):
    """granprix/eqNN/evento (QoS 1)."""

    equipo: int
    tipo: Literal["intervencion", "pit_ok", "reintento"]
    subtipo: Literal["fisica", "web", "teleoperacion", "software"] | None = None
    declarada: bool = True
    estacion: int | None = None

    @model_validator(mode="after")
    def _intervencion_lleva_subtipo(self) -> "EventoMsg":
        if self.tipo == "intervencion" and self.subtipo is None:
            raise ValueError("una intervención necesita 'subtipo'")
        return self


class VueltaMsg(Mensaje):
    """granprix/eqNN/vuelta (QoS 1).

    `estaciones` es opcional: si falta, Race Control infiere el recorrido de los pits.
    """

    equipo: int
    numero: int
    t_inicio: float
    t_fin: float
    estaciones: list[int] | None = None
