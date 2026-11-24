import csv

from pc_race.adaptadores.salida.ledger_sqlite import LedgerSqlite
from pc_race.aplicacion.puertos import EventoLedger


async def test_guarda_y_devuelve_en_orden(ledger):
    await ledger.agregar(EventoLedger("T1", 1.0, "tanda_creada", {"equipos": [7]}))
    await ledger.agregar(EventoLedger("T1", 2.0, "fase", {"accion": "carrera"}))
    await ledger.agregar(EventoLedger("T2", 3.0, "tanda_creada", {"equipos": [8]}))

    assert [e.tipo for e in await ledger.eventos("T1")] == ["tanda_creada", "fase"]
    assert (await ledger.eventos("T1"))[0].datos == {"equipos": [7]}
    assert await ledger.ultima_tanda() == "T2"


async def test_clave_repetida_no_se_guarda_dos_veces(ledger):
    evento = EventoLedger("T1", 1.0, "intervencion", {"equipo": 7}, clave="int:7:1.0")
    assert await ledger.agregar(evento) is True
    assert await ledger.agregar(evento) is False
    assert len(await ledger.eventos("T1")) == 1


async def test_eventos_sin_clave_no_se_deduplican(ledger):
    for _ in range(2):
        await ledger.agregar(EventoLedger("T1", 1.0, "fase", {"accion": "roja"}))
    assert len(await ledger.eventos("T1")) == 2


async def test_misma_clave_en_otra_tanda_es_otro_evento(ledger):
    assert await ledger.agregar(EventoLedger("T1", 1.0, "x", {}, clave="k"))
    assert await ledger.agregar(EventoLedger("T2", 1.0, "x", {}, clave="k"))


async def test_ledger_vacio(ledger):
    assert await ledger.ultima_tanda() is None


async def test_sobrevive_a_un_reinicio(tmp_path):
    ruta = tmp_path / "ledger.sqlite3"
    primero = LedgerSqlite(ruta)
    await primero.abrir()
    await primero.agregar(EventoLedger("T1", 1.0, "fase", {"accion": "carrera"}))
    await primero.cerrar()

    segundo = LedgerSqlite(ruta)
    await segundo.abrir()
    assert len(await segundo.eventos("T1")) == 1
    await segundo.cerrar()


async def test_exporta_a_csv(ledger, tmp_path):
    await ledger.agregar(EventoLedger("T1", 1.0, "intervencion", {"equipo": 7, "tipo": "fisica"}))
    destino = tmp_path / "t1.csv"
    assert await ledger.exportar_csv("T1", destino) == 1
    with destino.open(encoding="utf-8", newline="") as f:
        filas = list(csv.reader(f))
    assert filas[0] == ["tanda", "ts", "tipo", "datos"]
    assert filas[1][0] == "T1" and "fisica" in filas[1][3]
