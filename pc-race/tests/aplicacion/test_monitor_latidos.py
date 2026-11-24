from pc_race.aplicacion.monitor_latidos import MonitorLatidos


async def test_sin_latido_por_mas_de_3_s_marca_offline_y_avisa_una_vez(tablero):
    monitor = MonitorLatidos(tablero)
    await monitor.latido("estacion:2", 100.0)
    assert await monitor.revisar(103.0) == []  # justo en el umbral: aún en línea
    assert await monitor.revisar(103.5) == ["estacion:2"]
    assert await monitor.revisar(110.0) == []  # no repite el aviso
    assert len(tablero.avisos) == 1 and "estacion:2 OFFLINE" in tablero.avisos[0]


async def test_un_latido_nuevo_lo_devuelve_a_linea(tablero):
    monitor = MonitorLatidos(tablero)
    await monitor.latido("estacion:2", 100.0)
    await monitor.revisar(110.0)
    await monitor.latido("estacion:2", 111.0)
    assert "estacion:2" not in monitor.offline
    assert "volvió en línea" in tablero.avisos[-1]


async def test_last_will_marca_offline_de_inmediato(tablero):
    monitor = MonitorLatidos(tablero)
    await monitor.caida("estacion:3", 100.0)
    assert "estacion:3" in monitor.offline
