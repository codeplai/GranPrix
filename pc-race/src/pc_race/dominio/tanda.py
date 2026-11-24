from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from statistics import fmean
from typing import Any

from transitions import Machine, MachineError

from pc_race.dominio.errores import EquipoDesconocido, TransicionInvalida
from pc_race.dominio.intervencion import Intervencion, MotivoExencion
from pc_race.dominio.pit import Pit, PoseDock
from pc_race.dominio.ranking import MIN_VUELTAS_VALIDAS, ResumenEquipo
from pc_race.dominio.vuelta import Vuelta, evaluar_vuelta, pit_en_ventana


class Fase(StrEnum):
    PENDIENTE = "pendiente"
    CALENTAMIENTO = "calentamiento"
    CARRERA = "carrera"
    ROJA = "roja"
    FIN = "fin"


@dataclass(frozen=True)
class ReglasTanda:
    vueltas: int = 4
    duracion_max: float = 12 * 60.0
    calentamiento: float = 3 * 60.0
    estaciones: tuple[int, ...] = (1, 2, 3, 4)
    tolerancia_ts: float = 1.0
    min_vueltas_validas: int = MIN_VUELTAS_VALIDAS


@dataclass
class _Solicitud:
    ts: float
    pose: PoseDock
    pieza_trae: str | None


@dataclass
class _EquipoEnTanda:
    equipo: int
    intervenciones: list[Intervencion] = field(default_factory=list)
    vueltas: dict[int, Vuelta] = field(default_factory=dict)
    pits: list[Pit] = field(default_factory=list)
    solicitudes: dict[int, _Solicitud] = field(default_factory=dict)
    solicitudes_vistas: set[tuple[int, float]] = field(default_factory=set)
    pits_usados: set[int] = field(default_factory=set)  # índices en `pits` ya usados por una vuelta


_TRANSICIONES: list[Any] = [
    {"trigger": "ev_calentamiento", "source": "pendiente", "dest": "calentamiento"},
    {"trigger": "ev_carrera", "source": ["pendiente", "calentamiento"], "dest": "carrera"},
    {"trigger": "ev_roja", "source": "carrera", "dest": "roja"},
    {"trigger": "ev_verde", "source": "roja", "dest": "carrera"},
    {"trigger": "ev_fin", "source": ["calentamiento", "carrera", "roja"], "dest": "fin"},
]


class Tanda:
    """Una tanda: un grupo de equipos con la misma fase y el mismo reloj de carrera.

    El dominio no lee el reloj: cada operación recibe `ts` (segundos Unix).
    Durante la bandera roja el cronómetro de carrera se detiene (supuesto a confirmar).
    """

    state: str  # lo asigna `transitions`

    def __init__(
        self,
        tanda_id: str,
        equipos: Iterable[int],
        reglas: ReglasTanda | None = None,
    ) -> None:
        self.id = tanda_id
        self.reglas = reglas or ReglasTanda()
        self._equipos = {e: _EquipoEnTanda(e) for e in equipos}
        self._t_calentamiento: float | None = None
        self._t_carrera_inicio: float | None = None
        self._t_fin: float | None = None
        self._carrera_acumulada = 0.0
        self._tramo_inicio: float | None = None
        self._maquina = Machine(
            model=self,
            states=[f.value for f in Fase],
            transitions=_TRANSICIONES,
            initial=Fase.PENDIENTE.value,
            auto_transitions=False,
        )

    # ------------------------------------------------------------------ fases

    @property
    def fase(self) -> Fase:
        return Fase(self.state)

    @property
    def equipos(self) -> tuple[int, ...]:
        return tuple(sorted(self._equipos))

    def iniciar_calentamiento(self, ts: float) -> None:
        self._disparar("ev_calentamiento", ts)

    def iniciar_carrera(self, ts: float) -> None:
        self._disparar("ev_carrera", ts)

    def bandera_roja(self, ts: float) -> None:
        self._disparar("ev_roja", ts)

    def bandera_verde(self, ts: float) -> None:
        self._disparar("ev_verde", ts)

    def terminar(self, ts: float) -> None:
        self._disparar("ev_fin", ts)

    def _disparar(self, trigger: str, ts: float) -> None:
        try:
            getattr(self, trigger)(ts)
        except MachineError as error:
            raise TransicionInvalida(
                f"no se puede '{trigger}' desde la fase {self.state}"
            ) from error

    # Callbacks de `transitions` (se enlazan por nombre).
    def on_enter_calentamiento(self, ts: float) -> None:
        self._t_calentamiento = ts

    def on_enter_carrera(self, ts: float) -> None:
        self._tramo_inicio = ts
        if self._t_carrera_inicio is None:
            self._t_carrera_inicio = ts

    def on_exit_carrera(self, ts: float) -> None:
        if self._tramo_inicio is not None:
            self._carrera_acumulada += ts - self._tramo_inicio
            self._tramo_inicio = None

    def on_enter_fin(self, ts: float) -> None:
        self._t_fin = ts

    # ---------------------------------------------------------------- reloj

    def tiempo_carrera(self, ts: float) -> float:
        """Segundos de carrera transcurridos, sin contar la bandera roja."""
        en_curso = ts - self._tramo_inicio if self._tramo_inicio is not None else 0.0
        return self._carrera_acumulada + max(en_curso, 0.0)

    def calentamiento_agotado(self, ts: float) -> bool:
        return (
            self.fase is Fase.CALENTAMIENTO
            and self._t_calentamiento is not None
            and ts - self._t_calentamiento >= self.reglas.calentamiento
        )

    def carrera_agotada(self, ts: float) -> bool:
        return self.fase is Fase.CARRERA and self.tiempo_carrera(ts) >= self.reglas.duracion_max

    # ---------------------------------------------------------- intervenciones

    def registrar_intervencion(self, intervencion: Intervencion) -> Intervencion:
        """Guarda la intervención y decide si cuenta según la fase.

        Solo cuentan las ocurridas en carrera y sin motivo de exención. Si llega repetida
        (QoS 1) devuelve la ya guardada.
        """
        datos = self._equipo(intervencion.equipo)
        for existente in datos.intervenciones:
            if existente.clave == intervencion.clave:
                return existente

        exencion = intervencion.exencion or self._exencion_por_fase()
        registrada = replace(intervencion, exencion=exencion)
        datos.intervenciones.append(registrada)
        return registrada

    def _exencion_por_fase(self) -> MotivoExencion | None:
        match self.fase:
            case Fase.CARRERA:
                return None
            case Fase.PENDIENTE | Fase.CALENTAMIENTO:
                return MotivoExencion.AJUSTE_PREVIO
            case Fase.ROJA:
                return MotivoExencion.BANDERA_ROJA
            case Fase.FIN:
                return MotivoExencion.FUERA_DE_TANDA

    def intervenciones(self, equipo: int) -> tuple[Intervencion, ...]:
        return tuple(self._equipo(equipo).intervenciones)

    # -------------------------------------------------------------------- pits

    def registrar_solicitud(
        self, equipo: int, estacion: int, ts: float, pose: PoseDock, pieza_trae: str | None
    ) -> bool:
        """Guarda la solicitud del carrito. Devuelve False si no cuenta (fase sin carrera)."""
        datos = self._equipo(equipo)
        if not self._cuenta_carrera():
            return False
        if (estacion, ts) not in datos.solicitudes_vistas:  # QoS 1 puede duplicar
            datos.solicitudes_vistas.add((estacion, ts))
            datos.solicitudes[estacion] = _Solicitud(ts, pose, pieza_trae)
        return True

    def registrar_resultado(
        self,
        equipo: int,
        estacion: int,
        ts: float,
        ok: bool,
        pieza_dejo: str | None,
        t_cambio: float | None,
    ) -> Pit | None:
        """Cierra el pit con el resultado de la estación. None si no cuenta (fase sin carrera)."""
        datos = self._equipo(equipo)
        if not self._cuenta_carrera():
            return None
        for existente in datos.pits:
            if existente.estacion == estacion and existente.ts_resultado == ts:
                return existente  # resultado duplicado (QoS 1)
        solicitud = datos.solicitudes.pop(estacion, None)
        pit = Pit(
            equipo=equipo,
            estacion=estacion,
            ts_resultado=ts,
            ok=ok,
            pieza_trae=solicitud.pieza_trae if solicitud else None,
            pieza_dejo=pieza_dejo,
            t_cambio=t_cambio,
            pose=solicitud.pose if solicitud else None,
            ts_solicitud=solicitud.ts if solicitud else None,
        )
        datos.pits.append(pit)
        return pit

    def pits(self, equipo: int) -> tuple[Pit, ...]:
        return tuple(self._equipo(equipo).pits)

    # ----------------------------------------------------------------- vueltas

    def cerrar_vuelta(
        self,
        equipo: int,
        numero: int,
        t_inicio: float,
        t_fin: float,
        estaciones: Sequence[int] | None = None,
    ) -> Vuelta | None:
        """Valida y guarda la vuelta. None si no cuenta (fase sin carrera o equipo ya terminó).

        Una vuelta repetida (mismo número) devuelve la primera, sin cambios.
        """
        datos = self._equipo(equipo)
        if not self._cuenta_carrera():
            return None
        if numero in datos.vueltas:
            return datos.vueltas[numero]
        if len(datos.vueltas) >= self.reglas.vueltas:
            return None

        # Cada pit sirve a una sola vuelta: el último pit de una vuelta cae pegado al inicio de la
        # siguiente, y la tolerancia de reloj lo haría entrar también en ella.
        tol = self.reglas.tolerancia_ts
        disponibles = [(i, p) for i, p in enumerate(datos.pits) if i not in datos.pits_usados]
        vuelta = evaluar_vuelta(
            equipo=equipo,
            numero=numero,
            t_inicio=t_inicio,
            t_fin=t_fin,
            estaciones=estaciones,
            pits=[p for _, p in disponibles],
            orden=self.reglas.estaciones,
            tolerancia=tol,
        )
        datos.pits_usados.update(
            i for i, p in disponibles if pit_en_ventana(p, equipo, t_inicio, t_fin, tol)
        )
        datos.vueltas[numero] = vuelta
        return vuelta

    def vueltas(self, equipo: int) -> tuple[Vuelta, ...]:
        return tuple(sorted(self._equipo(equipo).vueltas.values(), key=lambda v: v.numero))

    def equipo_termino(self, equipo: int) -> bool:
        return len(self._equipo(equipo).vueltas) >= self.reglas.vueltas

    def todos_terminaron(self) -> bool:
        return all(self.equipo_termino(e) for e in self._equipos)

    # ----------------------------------------------------------------- ranking

    def resumenes(self) -> tuple[ResumenEquipo, ...]:
        return tuple(self._resumen(datos) for datos in self._equipos.values())

    def _resumen(self, datos: _EquipoEnTanda) -> ResumenEquipo:
        validas = [v for v in datos.vueltas.values() if v.valida]
        errores = [p.pose.error_lineal for p in datos.pits if p.ok and p.pose is not None]
        return ResumenEquipo(
            equipo=datos.equipo,
            puntos_intervencion=sum(i.puntos for i in datos.intervenciones),
            vueltas_validas=len(validas),
            tiempo_medio_vuelta=fmean(v.duracion for v in validas) if validas else None,
            error_pose_medio=fmean(errores) if errores else None,
        )

    # ----------------------------------------------------------------- interno

    def _cuenta_carrera(self) -> bool:
        """Pits y vueltas solo cuentan en carrera; en roja llegan mensajes que ya iban en vuelo."""
        return self.fase in (Fase.CARRERA, Fase.ROJA)

    def _equipo(self, equipo: int) -> _EquipoEnTanda:
        try:
            return self._equipos[equipo]
        except KeyError:
            raise EquipoDesconocido(f"el equipo {equipo} no está en la tanda {self.id}") from None
