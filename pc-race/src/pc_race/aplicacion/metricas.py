from collections import Counter


class Metricas:
    """Cuenta lo que Race Control descarta, para mostrarlo en el panel del juez."""

    def __init__(self) -> None:
        self.recibidos = 0
        self.invalidos: Counter[str] = Counter()  # por canal; mensaje mal formado
        self.descartados: Counter[str] = Counter()  # por motivo; mensaje válido que no aplica

    def contar_recibido(self) -> None:
        self.recibidos += 1

    def contar_invalido(self, canal: str) -> None:
        self.invalidos[canal] += 1

    def contar_descartado(self, motivo: str) -> None:
        self.descartados[motivo] += 1

    @property
    def total_invalidos(self) -> int:
        return sum(self.invalidos.values())
