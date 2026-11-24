from collections.abc import Iterable
from dataclasses import dataclass

MIN_VUELTAS_VALIDAS = 3


@dataclass(frozen=True)
class ResumenEquipo:
    equipo: int
    puntos_intervencion: int
    vueltas_validas: int
    tiempo_medio_vuelta: float | None
    error_pose_medio: float | None


@dataclass(frozen=True)
class Posicion:
    resumen: ResumenEquipo
    elegible: bool
    posicion: int | None  # None si no es elegible


def _clave(r: ResumenEquipo) -> tuple[int, int, float, float]:
    """Menos intervenciones; empate: más vueltas válidas, menor tiempo medio, menor error medio."""
    inf = float("inf")
    return (
        r.puntos_intervencion,
        -r.vueltas_validas,
        r.tiempo_medio_vuelta if r.tiempo_medio_vuelta is not None else inf,
        r.error_pose_medio if r.error_pose_medio is not None else inf,
    )


def calcular_ranking(
    resumenes: Iterable[ResumenEquipo], min_vueltas_validas: int = MIN_VUELTAS_VALIDAS
) -> tuple[Posicion, ...]:
    """Ordena los equipos. Los elegibles van primero; los empates exactos comparten posición
    (1, 1, 3). Los no elegibles se listan al final sin posición."""
    ordenados = sorted(resumenes, key=lambda r: (_clave(r), r.equipo))
    elegibles = [r for r in ordenados if r.vueltas_validas >= min_vueltas_validas]
    no_elegibles = [r for r in ordenados if r.vueltas_validas < min_vueltas_validas]

    resultado: list[Posicion] = []
    for indice, r in enumerate(elegibles):
        if indice > 0 and _clave(r) == _clave(elegibles[indice - 1]):
            posicion = resultado[-1].posicion
        else:
            posicion = indice + 1
        resultado.append(Posicion(resumen=r, elegible=True, posicion=posicion))
    resultado.extend(Posicion(resumen=r, elegible=False, posicion=None) for r in no_elegibles)
    return tuple(resultado)
