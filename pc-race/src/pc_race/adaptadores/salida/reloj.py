import time


class RelojSistema:
    """Hora del sistema. El NTP lo mantiene chrony (o el servicio de hora de Windows)."""

    def ahora(self) -> float:
        return time.time()
