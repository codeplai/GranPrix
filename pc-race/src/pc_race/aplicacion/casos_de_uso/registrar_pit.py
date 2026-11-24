from pc_race.aplicacion.reconstruccion import RESULTADO, SOLICITUD
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.pit import Pit, PoseDock


class RegistrarPit:
    """Un pit son dos mensajes: la solicitud del carrito (con su pose en el dock)
    y el resultado de la estación. Se emparejan por equipo y estación."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    async def solicitud(
        self, equipo: int, estacion: int, pose: PoseDock, pieza_trae: str | None, ts: float
    ) -> None:
        datos = {
            "equipo": equipo,
            "estacion": estacion,
            "dx": pose.dx,
            "dy": pose.dy,
            "dth": pose.dth,
            "pieza_trae": pieza_trae,
        }
        await self._sesion.registrar(SOLICITUD, datos, ts, f"sol:{equipo}:{estacion}:{ts}")

    async def resultado(
        self,
        equipo: int,
        estacion: int,
        ok: bool,
        pieza_dejo: str | None,
        t_cambio: float | None,
        ts: float,
    ) -> Pit | None:
        datos = {
            "equipo": equipo,
            "estacion": estacion,
            "ok": ok,
            "pieza_dejo": pieza_dejo,
            "t_cambio": t_cambio,
        }
        pit: Pit | None = await self._sesion.registrar(
            RESULTADO, datos, ts, f"res:{equipo}:{estacion}:{ts}"
        )
        await self._sesion.publicar_ranking()
        return pit
