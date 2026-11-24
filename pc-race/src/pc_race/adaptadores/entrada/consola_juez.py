import asyncio
import logging

from pc_race.aplicacion.casos_de_uso.calcular_ranking import CalcularRanking
from pc_race.aplicacion.casos_de_uso.declarar_bandera import DeclararBandera
from pc_race.aplicacion.casos_de_uso.iniciar_tanda import IniciarTanda
from pc_race.aplicacion.casos_de_uso.registrar_intervencion import RegistrarIntervencion
from pc_race.aplicacion.sesion import SesionCarrera
from pc_race.dominio.errores import ErrorDominio
from pc_race.dominio.intervencion import MotivoExencion, TipoIntervencion

log = logging.getLogger(__name__)

AYUDA = """comandos:
  tanda 1 2 3 [sin-calentamiento]   crea la tanda con esos equipos
  carrera | roja | verde | fin      cambia la fase
  int <equipo> <tipo> [declarada]   intervención vista por el juez
                                    (tipos: fisica web teleoperacion software)
  exenta <equipo> <tipo> <motivo>   acción que no cuenta (iniciar tablero pausa_juez)
  ranking | estado | ayuda | salir"""


class ConsolaJuez:
    """Control mínimo del juez por teclado, hasta que exista la ApiWeb (paso 4)."""

    def __init__(self, sesion: SesionCarrera) -> None:
        self._sesion = sesion
        self._iniciar = IniciarTanda(sesion)
        self._bandera = DeclararBandera(sesion)
        self._intervenciones = RegistrarIntervencion(sesion)
        self._ranking = CalcularRanking(sesion)

    async def ejecutar(self, linea: str) -> str:
        """Ejecuta un comando y devuelve el texto para mostrar al juez."""
        partes = linea.split()
        if not partes:
            return ""
        comando, args = partes[0].lower(), partes[1:]
        try:
            return await self._comando(comando, args)
        except (ErrorDominio, ValueError, IndexError) as error:
            return f"error: {error}"

    async def _comando(self, comando: str, args: list[str]) -> str:
        match comando:
            case "tanda":
                sin = "sin-calentamiento" in args
                equipos = [int(a) for a in args if a != "sin-calentamiento"]
                tanda_id = await self._iniciar.nueva(equipos, con_calentamiento=not sin)
                return f"tanda {tanda_id} creada"
            case "carrera":
                await self._iniciar.pasar_a_carrera()
            case "roja":
                await self._bandera.roja()
            case "verde":
                await self._bandera.verde()
            case "fin":
                await self._iniciar.terminar()
            case "int":
                equipo, tipo = int(args[0]), TipoIntervencion(args[1])
                declarada = len(args) > 2 and args[2] == "declarada"
                hecho = await self._intervenciones.desde_juez(equipo, tipo, declarada)
                return f"registrada: {hecho.puntos if hecho else 0} punto(s)"
            case "exenta":
                equipo, tipo = int(args[0]), TipoIntervencion(args[1])
                hecho = await self._intervenciones.desde_juez(
                    equipo, tipo, declarada=True, exencion=MotivoExencion(args[2])
                )
                return "registrada sin puntos" if hecho else "no registrada"
            case "ranking":
                return self._formato_ranking()
            case "estado":
                tanda = self._sesion.tanda
                if tanda is None:
                    return "sin tanda"
                ts = self._sesion.reloj.ahora()
                return f"{tanda.id}: {tanda.fase}, carrera {tanda.tiempo_carrera(ts):.0f} s"
            case "ayuda":
                return AYUDA
            case _:
                return f"comando desconocido: {comando}. Escribe 'ayuda'."
        return "ok"

    def _formato_ranking(self) -> str:
        lineas = []
        for p in self._ranking.calcular():
            r = p.resumen
            pos = str(p.posicion) if p.posicion is not None else "-"
            tmedio = f"{r.tiempo_medio_vuelta:.1f} s" if r.tiempo_medio_vuelta is not None else "-"
            lineas.append(
                f"{pos:>2}  equipo {r.equipo:02d}  interv {r.puntos_intervencion}  "
                f"vueltas {r.vueltas_validas}  t medio {tmedio}"
                f"{'' if p.elegible else '  (no elegible)'}"
            )
        return "\n".join(lineas) or "sin equipos"

    async def leer(self) -> None:
        """Lee comandos de la terminal hasta 'salir' o fin de entrada."""
        print(AYUDA)
        while True:
            try:
                linea = await asyncio.to_thread(input, "juez> ")
            except EOFError:
                return
            if linea.strip().lower() == "salir":
                return
            respuesta = await self.ejecutar(linea)
            if respuesta:
                print(respuesta)
