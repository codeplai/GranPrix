"""ApiWeb: se llama a la app ASGI directamente, sin abrir puertos."""

import httpx
import pytest

from pc_race.adaptadores.entrada.api_web import crear_app
from pc_race.adaptadores.salida.tablero_memoria import TableroEnMemoria
from pc_race.aplicacion.metricas import Metricas
from pc_race.aplicacion.monitor_latidos import MonitorLatidos
from pc_race.aplicacion.sesion import SesionCarrera


@pytest.fixture
def tablero_real():
    return TableroEnMemoria()


@pytest.fixture
def sesion_api(ledger, publicador, tablero_real, reloj):
    return SesionCarrera(ledger, publicador, tablero_real, reloj)


def cliente(sesion, tablero, token=None):
    app = crear_app(sesion, tablero, Metricas(), MonitorLatidos(tablero), token)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://juez")


async def test_estado_sin_tanda(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real) as c:
        datos = (await c.get("/api/estado")).json()
    assert datos["tanda"] is None and datos["ranking"] == [] and datos["fase"] is None


async def test_flujo_del_juez_por_http(sesion_api, tablero_real, publicador):
    async with cliente(sesion_api, tablero_real) as c:
        r = await c.post("/api/tanda", json={"equipos": [7, 8], "con_calentamiento": True})
        assert r.status_code == 201
        assert (await c.get("/api/estado")).json()["fase"] == "calentamiento"

        assert (await c.post("/api/carrera")).json()["fase"] == "carrera"
        assert (await c.post("/api/bandera/roja")).json()["fase"] == "roja"
        assert (await c.post("/api/bandera/verde")).json()["fase"] == "carrera"

        r = await c.post("/api/intervencion", json={"equipo": 7, "tipo": "web"})
        assert r.status_code == 201 and r.json() == {"puntos": 4}  # no declarada: 1 + 3

        ranking = (await c.get("/api/estado")).json()["ranking"]
        por_equipo = {f["equipo"]: f for f in ranking}
        assert por_equipo[7]["intervenciones"] == 4 and por_equipo[8]["intervenciones"] == 0
        assert not por_equipo[7]["elegible"]  # sin vueltas válidas todavía

        assert (await c.post("/api/fin")).json()["fase"] == "fin"
    assert publicador.banderas == ["verde", "roja", "verde"]


async def test_exencion_no_suma(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real) as c:
        await c.post("/api/tanda", json={"equipos": [7], "con_calentamiento": False})
        r = await c.post(
            "/api/intervencion",
            json={"equipo": 7, "tipo": "web", "declarada": True, "exencion": "tablero"},
        )
    assert r.json() == {"puntos": 0}


async def test_errores_de_dominio_son_http_claros(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real) as c:
        assert (await c.post("/api/carrera")).status_code == 404  # sin tanda
        await c.post("/api/tanda", json={"equipos": [7]})
        assert (await c.post("/api/tanda", json={"equipos": [8]})).status_code == 409
        assert (await c.post("/api/bandera/roja")).status_code == 409  # aún en calentamiento
        r = await c.post("/api/intervencion", json={"equipo": 99, "tipo": "web"})
        assert r.status_code == 422 and "99" in r.json()["detail"]


async def test_datos_mal_formados_son_422(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real) as c:
        assert (await c.post("/api/tanda", json={"equipos": []})).status_code == 422
        r = await c.post("/api/intervencion", json={"equipo": 1, "tipo": "magica"})
        assert r.status_code == 422


async def test_con_token_las_acciones_lo_exigen_pero_la_lectura_no(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real, token="secreto") as c:
        assert (await c.get("/api/estado")).status_code == 200
        assert (await c.post("/api/tanda", json={"equipos": [7]})).status_code == 401
        mal = await c.post("/api/tanda", json={"equipos": [7]}, headers={"X-Token": "otro"})
        assert mal.status_code == 401
        bien = await c.post("/api/tanda", json={"equipos": [7]}, headers={"X-Token": "secreto"})
        assert bien.status_code == 201


async def test_la_pagina_del_tablero_se_sirve(sesion_api, tablero_real):
    async with cliente(sesion_api, tablero_real) as c:
        r = await c.get("/")
    assert r.status_code == 200 and "Race Control" in r.text and "/ws" in r.text


async def test_tablero_avisa_a_los_suscriptores_en_cada_cambio():
    tablero = TableroEnMemoria()
    cola = tablero.suscribir()
    assert cola.empty()
    await tablero.avisar("estacion:2 OFFLINE")
    assert not cola.empty()
    cola.get_nowait()
    await tablero.publicar_ranking("T1", ())
    await tablero.publicar_ranking("T1", ())  # no se acumulan señales
    assert cola.qsize() == 1
    tablero.desuscribir(cola)
    await tablero.avisar("otro")
    assert cola.qsize() == 1
