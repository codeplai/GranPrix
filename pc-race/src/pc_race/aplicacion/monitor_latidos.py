from pc_race.aplicacion.puertos import PublicadorTablero

UMBRAL_LATIDO = 3.0  # segundos sin noticias antes de marcar OFFLINE


class MonitorLatidos:
    """Marca OFFLINE a estaciones y carritos que dejan de dar señales y avisa al juez.

    Cualquier mensaje de la estación (estado) o del carrito (telemetría) cuenta como latido,
    así que deben publicar al menos una vez cada pocos segundos. Usa la hora de llegada
    a Race Control, no la del mensaje, para no depender de relojes ajenos.
    """

    def __init__(self, tablero: PublicadorTablero, umbral: float = UMBRAL_LATIDO) -> None:
        self._tablero = tablero
        self._umbral = umbral
        self._ultimo: dict[str, float] = {}
        self._offline: set[str] = set()

    @property
    def offline(self) -> frozenset[str]:
        return frozenset(self._offline)

    async def latido(self, clave: str, ahora: float) -> None:
        self._ultimo[clave] = ahora
        if clave in self._offline:
            self._offline.discard(clave)
            await self._tablero.avisar(f"{clave} volvió en línea")

    async def caida(self, clave: str, ahora: float) -> None:
        """El broker avisó (Last Will) o la estación dijo OFFLINE."""
        self._ultimo[clave] = ahora
        await self._marcar_offline(clave, "avisó OFFLINE")

    async def revisar(self, ahora: float) -> list[str]:
        """Marca OFFLINE a lo que lleva más del umbral callado. Devuelve las claves nuevas."""
        nuevas = [
            clave
            for clave, visto in self._ultimo.items()
            if clave not in self._offline and ahora - visto > self._umbral
        ]
        for clave in nuevas:
            await self._marcar_offline(clave, f"sin latido por más de {self._umbral:g} s")
        return nuevas

    async def _marcar_offline(self, clave: str, motivo: str) -> None:
        if clave in self._offline:
            return
        self._offline.add(clave)
        await self._tablero.avisar(f"{clave} OFFLINE ({motivo})")
