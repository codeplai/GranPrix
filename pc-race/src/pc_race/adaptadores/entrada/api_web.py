"""ApiWeb: tablero del juez (HTTP + WebSocket). Es un adaptador de entrada: solo traduce
peticiones a casos de uso y estado a JSON."""

import asyncio
import hmac
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from pc_race.adaptadores.salida.tablero_memoria import TableroEnMemoria
from pc_race.aplicacion.casos_de_uso.declarar_bandera import DeclararBandera
from pc_race.aplicacion.casos_de_uso.iniciar_tanda import IniciarTanda, TandaEnCurso
from pc_race.aplicacion.casos_de_uso.registrar_intervencion import RegistrarIntervencion
from pc_race.aplicacion.metricas import Metricas
from pc_race.aplicacion.monitor_latidos import MonitorLatidos
from pc_race.aplicacion.sesion import SesionCarrera, SinTandaActiva
from pc_race.dominio.errores import ErrorDominio, TransicionInvalida
from pc_race.dominio.intervencion import MotivoExencion, TipoIntervencion

PAGINA = Path(__file__).with_name("tablero.html")
AVISOS_VISIBLES = 20


class NuevaTanda(BaseModel):
    equipos: list[int] = Field(min_length=1)
    con_calentamiento: bool = True


class NuevaIntervencion(BaseModel):
    equipo: int
    tipo: Literal["fisica", "web", "teleoperacion", "software"]
    declarada: bool = False  # lo que el juez ve en el video y el equipo no declaró
    exencion: Literal["iniciar", "tablero", "pausa_juez"] | None = None


def _estado_http(error: ErrorDominio) -> int:
    if isinstance(error, SinTandaActiva):
        return 404
    if isinstance(error, TandaEnCurso | TransicionInvalida):
        return 409
    return 422


def crear_app(
    sesion: SesionCarrera,
    tablero: TableroEnMemoria,
    metricas: Metricas,
    monitor: MonitorLatidos,
    token: str | None = None,
) -> FastAPI:
    """`token`: si se da, las acciones del juez (POST) exigen la cabecera X-Token."""
    app = FastAPI(title="Race Control", docs_url="/api/docs", openapi_url="/api/openapi.json")
    iniciar = IniciarTanda(sesion)
    bandera = DeclararBandera(sesion)
    intervenciones = RegistrarIntervencion(sesion)

    def snapshot() -> dict[str, Any]:
        tanda = sesion.tanda
        ahora = sesion.reloj.ahora()
        ranking = [
            {
                "posicion": p.posicion,
                "equipo": p.resumen.equipo,
                "intervenciones": p.resumen.puntos_intervencion,
                "vueltas_validas": p.resumen.vueltas_validas,
                "tiempo_medio": p.resumen.tiempo_medio_vuelta,
                "error_pose": p.resumen.error_pose_medio,
                "elegible": p.elegible,
            }
            for p in (sesion.ranking() if tanda else ())
        ]
        return {
            "tanda": tanda.id if tanda else None,
            "fase": tanda.fase.value if tanda else None,
            "t_carrera": tanda.tiempo_carrera(ahora) if tanda else 0.0,
            "duracion_max": sesion.reglas.duracion_max,
            "equipos": list(tanda.equipos) if tanda else [],
            "ranking": ranking,
            "avisos": list(tablero.avisos)[-AVISOS_VISIBLES:],
            "offline": sorted(monitor.offline),
            "metricas": {
                "recibidos": metricas.recibidos,
                "invalidos": metricas.total_invalidos,
                "invalidos_por_canal": dict(metricas.invalidos),
                "descartados": dict(metricas.descartados),
            },
        }

    def exigir_token(x_token: Annotated[str | None, Header()] = None) -> None:
        if token is not None and not hmac.compare_digest(x_token or "", token):
            raise HTTPException(status_code=401, detail="token inválido")

    juez = [Depends(exigir_token)]

    @app.exception_handler(ErrorDominio)
    async def _error_dominio(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ErrorDominio)
        return JSONResponse({"detail": str(error)}, status_code=_estado_http(error))

    @app.get("/", response_class=HTMLResponse)
    async def pagina() -> str:
        return PAGINA.read_text(encoding="utf-8")

    @app.get("/api/estado")
    async def estado() -> dict[str, Any]:
        return snapshot()

    @app.post("/api/tanda", dependencies=juez, status_code=201)
    async def crear_tanda(datos: NuevaTanda) -> dict[str, str]:
        tanda_id = await iniciar.nueva(datos.equipos, datos.con_calentamiento)
        return {"tanda": tanda_id}

    @app.post("/api/carrera", dependencies=juez)
    async def iniciar_carrera() -> dict[str, Any]:
        await iniciar.pasar_a_carrera()
        return snapshot()

    @app.post("/api/fin", dependencies=juez)
    async def terminar() -> dict[str, Any]:
        await iniciar.terminar()
        return snapshot()

    @app.post("/api/bandera/roja", dependencies=juez)
    async def bandera_roja() -> dict[str, Any]:
        await bandera.roja()
        return snapshot()

    @app.post("/api/bandera/verde", dependencies=juez)
    async def bandera_verde() -> dict[str, Any]:
        await bandera.verde()
        return snapshot()

    @app.post("/api/intervencion", dependencies=juez, status_code=201)
    async def registrar_intervencion(datos: NuevaIntervencion) -> dict[str, int]:
        hecho = await intervenciones.desde_juez(
            datos.equipo,
            TipoIntervencion(datos.tipo),
            datos.declarada,
            MotivoExencion(datos.exencion) if datos.exencion else None,
        )
        return {"puntos": hecho.puntos if hecho else 0}

    @app.websocket("/ws")
    async def tablero_ws(ws: WebSocket) -> None:
        """Empuja un snapshot al conectar, en cada cambio y cada segundo (para el cronómetro)."""
        await ws.accept()
        cola = tablero.suscribir()
        try:
            while True:
                await ws.send_json(snapshot())
                try:
                    await asyncio.wait_for(cola.get(), timeout=1.0)
                except TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            tablero.desuscribir(cola)

    return app
