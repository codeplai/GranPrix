class ErrorDominio(Exception):
    """Base de los errores que el dominio señala."""


class TransicionInvalida(ErrorDominio):
    """La tanda no puede pasar a esa fase desde la fase actual."""


class EquipoDesconocido(ErrorDominio):
    """El equipo no participa en la tanda."""


class VueltaInvalida(ErrorDominio):
    """Los datos de la vuelta son incoherentes (por ejemplo, termina antes de empezar)."""
