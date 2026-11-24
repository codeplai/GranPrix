"""Genera los JSON Schema a partir de los modelos: python -m contrato.esquemas [carpeta]."""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from contrato import modelos

MODELOS: tuple[type[BaseModel], ...] = (
    modelos.EstadoCarreraMsg,
    modelos.BanderaMsg,
    modelos.TurnoCarritoMsg,
    modelos.TurnoEstacionMsg,
    modelos.EstadoEstacionMsg,
    modelos.ResultadoMsg,
    modelos.SolicitudMsg,
    modelos.TelemetriaMsg,
    modelos.EventoMsg,
    modelos.VueltaMsg,
)


def generar(carpeta: Path) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    escritos = []
    for modelo in MODELOS:
        ruta = carpeta / f"{modelo.__name__}.schema.json"
        ruta.write_text(
            json.dumps(modelo.model_json_schema(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        escritos.append(ruta)
    return escritos


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "schemas"
    for ruta in generar(destino):
        print(ruta)
