from pc_race.aplicacion.reconstruccion import INTERVENCION
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.intervencion import Intervencion, MotivoExencion, Origen, TipoIntervencion


class RegistrarIntervencion:
    """Guarda una intervención del carrito o del juez y actualiza el ranking.

    Si cuenta o no lo decide la Tanda según su fase (ver `Tanda.registrar_intervencion`).
    """

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion

    async def desde_carrito(
        self, equipo: int, tipo: TipoIntervencion, declarada: bool, ts: float
    ) -> Intervencion | None:
        return await self._registrar(equipo, tipo, declarada, Origen.CARRITO, None, ts)

    async def desde_juez(
        self,
        equipo: int,
        tipo: TipoIntervencion,
        declarada: bool = False,
        exencion: MotivoExencion | None = None,
    ) -> Intervencion | None:
        """El juez la vio en el video. `declarada=False` suma la penalización.
        Con `exencion` registra una acción que no cuenta (iniciar, tablero, pausa del juez)."""
        return await self._registrar(
            equipo, tipo, declarada, Origen.JUEZ, exencion, self._sesion.reloj.ahora()
        )

    async def _registrar(
        self,
        equipo: int,
        tipo: TipoIntervencion,
        declarada: bool,
        origen: Origen,
        exencion: MotivoExencion | None,
        ts: float,
    ) -> Intervencion | None:
        datos = {
            "equipo": equipo,
            "tipo": tipo.value,
            "declarada": declarada,
            "origen": origen.value,
            "exencion": exencion.value if exencion else None,
        }
        clave = f"int:{equipo}:{ts}:{tipo.value}:{origen.value}"
        efecto: Intervencion | None = await self._sesion.registrar(INTERVENCION, datos, ts, clave)
        await self._sesion.publicar_ranking()
        return efecto
