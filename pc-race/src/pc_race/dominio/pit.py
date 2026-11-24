import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PoseDock:
    """Pose del carrito respecto al dock. dx, dy en metros; dth en grados."""

    dx: float
    dy: float
    dth: float

    @property
    def error_lineal(self) -> float:
        return math.hypot(self.dx, self.dy)


@dataclass(frozen=True)
class Pit:
    """Una parada en una estación: la solicitud del carrito más el resultado de la estación."""

    equipo: int
    estacion: int
    ts_resultado: float
    ok: bool
    pieza_trae: str | None = None
    pieza_dejo: str | None = None
    t_cambio: float | None = None
    pose: PoseDock | None = None
    ts_solicitud: float | None = None
