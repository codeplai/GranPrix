from dataclasses import dataclass, field

import pytest

from pc_race.adaptadores.salida.ledger_sqlite import LedgerSqlite
from pc_race.aplicacion.sesion import SesionCarrera


class RelojFalso:
    def __init__(self, ahora: float = 1_000.0) -> None:
        self._ahora = ahora

    def ahora(self) -> float:
        return self._ahora

    def avanzar(self, segundos: float) -> None:
        self._ahora += segundos


@dataclass
class PublicadorGrabado:
    estados: list = field(default_factory=list)
    banderas: list = field(default_factory=list)
    turnos: list = field(default_factory=list)

    async def publicar_estado(self, tanda_id, fase, equipos, t_carrera, ts):
        self.estados.append((tanda_id, fase.value, tuple(equipos)))

    async def publicar_bandera(self, bandera, ts):
        self.banderas.append(bandera.value)

    async def publicar_turno_carrito(self, equipo, autorizado, tanda_id, ts):
        self.turnos.append((equipo, autorizado))


@dataclass
class TableroGrabado:
    rankings: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    async def publicar_ranking(self, tanda_id, ranking):
        self.rankings.append(tuple(ranking))

    async def avisar(self, mensaje):
        self.avisos.append(mensaje)


@pytest.fixture
def reloj():
    return RelojFalso()


@pytest.fixture
def publicador():
    return PublicadorGrabado()


@pytest.fixture
def tablero():
    return TableroGrabado()


@pytest.fixture
async def ledger(tmp_path):
    ledger = LedgerSqlite(tmp_path / "ledger.sqlite3")
    await ledger.abrir()
    yield ledger
    await ledger.cerrar()


@pytest.fixture
def sesion(ledger, publicador, tablero, reloj):
    return SesionCarrera(ledger, publicador, tablero, reloj)
