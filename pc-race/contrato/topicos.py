"""Nombres de tópicos del contrato y su interpretación."""

import re
from dataclasses import dataclass
from typing import Literal

RAIZ = "granprix"

# Suscripciones de Race Control. MQTT no admite comodín dentro de un nivel ("eq+"),
# por eso los carritos se reciben con "+" y se filtran con RUTA_CARRITO.
SUSCRIPCIONES = (
    f"{RAIZ}/estacion/+/estado",
    f"{RAIZ}/estacion/+/solicitud",
    f"{RAIZ}/estacion/+/resultado",
    f"{RAIZ}/+/telemetria",
    f"{RAIZ}/+/evento",
    f"{RAIZ}/+/vuelta",
)

_RUTA_ESTACION = re.compile(rf"^{RAIZ}/estacion/(\d+)/(estado|solicitud|resultado)$")
_RUTA_CARRITO = re.compile(rf"^{RAIZ}/eq(\d{{2}})/(telemetria|evento|vuelta)$")


def topico_estado_carrera() -> str:
    return f"{RAIZ}/carrera/estado"


def topico_bandera() -> str:
    return f"{RAIZ}/carrera/bandera"


def topico_turno_estacion(estacion: int) -> str:
    return f"{RAIZ}/estacion/{estacion}/turno"


def topico_turno_carrito(equipo: int) -> str:
    return f"{RAIZ}/eq{equipo:02d}/turno"


@dataclass(frozen=True)
class Ruta:
    origen: Literal["estacion", "carrito"]
    numero: int
    canal: str


def interpretar(topico: str) -> Ruta | None:
    """Devuelve de dónde viene un tópico de entrada, o None si no es de los esperados."""
    if m := _RUTA_ESTACION.match(topico):
        return Ruta("estacion", int(m.group(1)), m.group(2))
    if m := _RUTA_CARRITO.match(topico):
        return Ruta("carrito", int(m.group(1)), m.group(2))
    return None
