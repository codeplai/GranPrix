from dataclasses import dataclass
from enum import StrEnum

# Cada intervención cuenta 1. Si el juez la ve en el video y el equipo no la declaró,
# suma además 3 (total 4). Supuesto a confirmar con el reglamento.
PUNTOS_BASE = 1
PENALIZACION_NO_DECLARADA = 3


class TipoIntervencion(StrEnum):
    FISICA = "fisica"
    WEB = "web"
    TELEOPERACION = "teleoperacion"
    SOFTWARE = "software"


class Origen(StrEnum):
    CARRITO = "carrito"
    JUEZ = "juez"


class MotivoExencion(StrEnum):
    """Acciones que el reglamento no cuenta como intervención."""

    INICIAR = "iniciar"
    TABLERO = "tablero"
    AJUSTE_PREVIO = "ajuste_previo"
    PAUSA_JUEZ = "pausa_juez"
    BANDERA_ROJA = "bandera_roja"
    FUERA_DE_TANDA = "fuera_de_tanda"


@dataclass(frozen=True)
class Intervencion:
    equipo: int
    tipo: TipoIntervencion
    ts: float
    declarada: bool = True
    origen: Origen = Origen.CARRITO
    exencion: MotivoExencion | None = None

    @property
    def cuenta(self) -> bool:
        return self.exencion is None

    @property
    def puntos(self) -> int:
        if not self.cuenta:
            return 0
        return PUNTOS_BASE + (0 if self.declarada else PENALIZACION_NO_DECLARADA)

    @property
    def clave(self) -> tuple[int, float, TipoIntervencion, Origen]:
        """Identifica el mismo evento si llega duplicado (QoS 1)."""
        return (self.equipo, self.ts, self.tipo, self.origen)
