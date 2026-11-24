import csv
import json
from pathlib import Path

import aiosqlite

from pc_race.aplicacion.puertos import EventoLedger

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tanda_id TEXT NOT NULL,
    ts       REAL NOT NULL,
    tipo     TEXT NOT NULL,
    datos    TEXT NOT NULL,
    clave    TEXT,
    UNIQUE (tanda_id, clave)
);
CREATE INDEX IF NOT EXISTS ix_eventos_tanda ON eventos (tanda_id, id);
"""


class LedgerSqlite:
    """Ledger durable. Sobrevive a un reinicio y se exporta a CSV."""

    def __init__(self, ruta: str | Path) -> None:
        self._ruta = str(ruta)
        self._db: aiosqlite.Connection | None = None

    async def abrir(self) -> None:
        self._db = await aiosqlite.connect(self._ruta)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_ESQUEMA)
        await self._db.commit()

    async def cerrar(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conexion(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("el ledger no está abierto: llamar a abrir()")
        return self._db

    async def agregar(self, evento: EventoLedger) -> bool:
        cursor = await self._conexion.execute(
            "INSERT OR IGNORE INTO eventos (tanda_id, ts, tipo, datos, clave)"
            " VALUES (?, ?, ?, ?, ?)",
            (evento.tanda_id, evento.ts, evento.tipo, json.dumps(evento.datos), evento.clave),
        )
        await self._conexion.commit()
        return cursor.rowcount == 1

    async def eventos(self, tanda_id: str) -> list[EventoLedger]:
        cursor = await self._conexion.execute(
            "SELECT tanda_id, ts, tipo, datos, clave FROM eventos WHERE tanda_id = ? ORDER BY id",
            (tanda_id,),
        )
        return [
            EventoLedger(tanda, ts, tipo, json.loads(datos), clave)
            for tanda, ts, tipo, datos, clave in await cursor.fetchall()
        ]

    async def ultima_tanda(self) -> str | None:
        cursor = await self._conexion.execute(
            "SELECT tanda_id FROM eventos ORDER BY id DESC LIMIT 1"
        )
        fila = await cursor.fetchone()
        return str(fila[0]) if fila else None

    async def exportar_csv(self, tanda_id: str, destino: str | Path) -> int:
        """Escribe los eventos de la tanda en un CSV. Devuelve cuántos escribió."""
        eventos = await self.eventos(tanda_id)
        with Path(destino).open("w", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["tanda", "ts", "tipo", "datos"])
            for e in eventos:
                datos = json.dumps(e.datos, ensure_ascii=False)
                escritor.writerow([e.tanda_id, e.ts, e.tipo, datos])
        return len(eventos)
