from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pc_race.dominio.errores import VueltaInvalida
from pc_race.dominio.pit import Pit


@dataclass(frozen=True)
class Vuelta:
    equipo: int
    numero: int
    t_inicio: float
    t_fin: float
    estaciones: tuple[int, ...]
    valida: bool

    @property
    def duracion(self) -> float:
        return self.t_fin - self.t_inicio


def pit_en_ventana(pit: Pit, equipo: int, t_inicio: float, t_fin: float, tolerancia: float) -> bool:
    """El pit es ok, del equipo, y cae en la vuelta (con tolerancia por el reloj ajeno)."""
    return (
        pit.equipo == equipo
        and pit.ok
        and t_inicio - tolerancia <= pit.ts_resultado <= t_fin + tolerancia
    )


def _pits_ok_en_ventana(
    pits: Iterable[Pit], equipo: int, t_inicio: float, t_fin: float, tolerancia: float
) -> list[Pit]:
    return sorted(
        (p for p in pits if pit_en_ventana(p, equipo, t_inicio, t_fin, tolerancia)),
        key=lambda p: p.ts_resultado,
    )


def inferir_recorrido(
    pits: Iterable[Pit], equipo: int, t_inicio: float, t_fin: float, tolerancia: float
) -> tuple[int, ...]:
    """Orden de estaciones por las que pasó el equipo, según sus pits ok en la ventana."""
    recorrido: list[int] = []
    for p in _pits_ok_en_ventana(pits, equipo, t_inicio, t_fin, tolerancia):
        if not recorrido or recorrido[-1] != p.estacion:
            recorrido.append(p.estacion)
    return tuple(recorrido)


def evaluar_vuelta(
    *,
    equipo: int,
    numero: int,
    t_inicio: float,
    t_fin: float,
    estaciones: Sequence[int] | None,
    pits: Iterable[Pit],
    orden: Sequence[int],
    tolerancia: float,
) -> Vuelta:
    """Una vuelta es válida si el carrito pasó por las estaciones en orden
    y cada pit tiene un resultado ok dentro de la ventana de la vuelta.

    Si el carrito no informa `estaciones`, el recorrido se infiere de los pits.
    `tolerancia` (segundos) absorbe la diferencia de reloj entre máquinas. Quien llama pasa solo
    los pits que ninguna vuelta anterior usó (ver `Tanda.cerrar_vuelta`).
    """
    if t_fin <= t_inicio:
        raise VueltaInvalida(f"vuelta {numero} del equipo {equipo} termina antes de empezar")

    pits = list(pits)
    if estaciones is None:
        recorrido = inferir_recorrido(pits, equipo, t_inicio, t_fin, tolerancia)
    else:
        recorrido = tuple(estaciones)
    en_orden = recorrido == tuple(orden)

    pits_ok = _pits_ok_en_ventana(pits, equipo, t_inicio, t_fin, tolerancia)
    pits_completos = all(any(p.estacion == e for p in pits_ok) for e in orden)

    return Vuelta(
        equipo=equipo,
        numero=numero,
        t_inicio=t_inicio,
        t_fin=t_fin,
        estaciones=recorrido,
        valida=en_orden and pits_completos,
    )
