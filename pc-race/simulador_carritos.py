"""Simulador de carritos y estaciones para probar Race Control contra un Mosquitto real.

Lanza N carritos falsos (uno por conexión MQTT) y las 4 estaciones. Cada carrito espera la
fase "carrera", recorre las 4 estaciones en orden, pide pit, cierra vueltas y de vez en cuando
declara una intervención. Las estaciones contestan cada solicitud con un resultado (a veces
fallan una vez y el pit se reintenta).

    python simulador_carritos.py --host localhost --carritos 10 --velocidad 20

`--velocidad 20` comprime los tiempos 20 veces. La clave del broker, si hace falta, va en la
variable de entorno GRANPRIX_MQTT_CLAVE; nunca como argumento.
"""

import argparse
import asyncio
import contextlib
import json
import os
import random
import sys
import time

import aiomqtt

ESTACIONES = (1, 2, 3, 4)
VUELTAS = 4


def _json(**campos: object) -> str:
    return json.dumps({"v": 1, "ts": time.time(), **campos})


def _cliente(
    args: argparse.Namespace, identificador: str, will: aiomqtt.Will | None = None
) -> aiomqtt.Client:
    return aiomqtt.Client(
        hostname=args.host,
        port=args.port,
        username=args.usuario,
        password=os.environ.get("GRANPRIX_MQTT_CLAVE"),
        identifier=identificador,
        will=will,
    )


async def estaciones(args: argparse.Namespace, rng: random.Random) -> None:
    """Las 4 estaciones: latido cada segundo y resultado por cada solicitud."""
    will = aiomqtt.Will(
        "granprix/estacion/1/estado", json.dumps({"v": 1, "ts": 0, "estado": "OFFLINE"}), qos=1
    )
    async with _cliente(args, "sim-estaciones", will=will) as c:
        await c.subscribe("granprix/estacion/+/solicitud", qos=1)

        async def latidos() -> None:
            while True:
                for n in ESTACIONES:
                    await c.publish(
                        f"granprix/estacion/{n}/estado", _json(estado="LIBRE"), qos=1, retain=True
                    )
                await asyncio.sleep(1.0)

        async def atender(topico: str, solicitud: dict[str, object]) -> None:
            n = int(topico.split("/")[2])
            t_cambio = rng.uniform(4.0, 7.0)
            intentos = 1 if rng.random() > 0.08 else 2  # a veces falla una vez y se reintenta
            for intento in range(intentos):
                await asyncio.sleep(t_cambio / args.velocidad)
                ok = intento == intentos - 1
                await c.publish(
                    f"granprix/estacion/{n}/resultado",
                    _json(equipo=solicitud["equipo"], ok=ok, pieza_dejo="B", t_cambio=t_cambio),
                    qos=1,
                )

        tarea = asyncio.create_task(latidos())
        pendientes: set[asyncio.Task[None]] = set()
        try:
            async for mensaje in c.messages:
                cuerpo = mensaje.payload
                if isinstance(cuerpo, bytes | str):
                    t = asyncio.create_task(atender(str(mensaje.topic), json.loads(cuerpo)))
                    pendientes.add(t)
                    t.add_done_callback(pendientes.discard)
        finally:
            tarea.cancel()


async def carrito(
    args: argparse.Namespace, equipo: int, rng: random.Random, resumen: dict[int, int]
) -> None:
    base = f"granprix/eq{equipo:02d}"
    async with _cliente(args, f"sim-carrito{equipo:02d}") as c:
        activo = asyncio.Event()
        await c.subscribe("granprix/carrera/estado", qos=1)

        async def vigilar_fase() -> None:
            async for mensaje in c.messages:
                if isinstance(mensaje.payload, bytes | str):
                    estado = json.loads(mensaje.payload)
                    if equipo in estado.get("equipos", []) and estado.get("fase") == "carrera":
                        activo.set()

        async def telemetria() -> None:
            while True:
                await c.publish(
                    f"{base}/telemetria",
                    _json(equipo=equipo, bateria=rng.uniform(60, 100), velocidad=0.4),
                    qos=0,
                )
                await asyncio.sleep(0.2)  # 5 Hz

        tareas = [asyncio.create_task(vigilar_fase()), asyncio.create_task(telemetria())]
        try:
            await activo.wait()
            for numero in range(1, VUELTAS + 1):
                t_inicio = time.time()
                for estacion in ESTACIONES:
                    await asyncio.sleep(rng.uniform(6, 10) / args.velocidad)  # viaje al dock
                    pose = {
                        "dx": rng.gauss(0, 0.015),
                        "dy": rng.gauss(0, 0.015),
                        "dth": rng.gauss(0, 2.0),
                    }
                    await c.publish(
                        f"granprix/estacion/{estacion}/solicitud",
                        _json(equipo=equipo, dock=estacion, pose=pose, pieza_trae="A"),
                        qos=1,
                    )
                    await asyncio.sleep(14.0 / args.velocidad)  # espera el cambio (con reintento)
                if rng.random() < args.prob_intervencion:
                    await c.publish(
                        f"{base}/evento",
                        _json(
                            equipo=equipo,
                            tipo="intervencion",
                            subtipo=rng.choice(["fisica", "web", "teleoperacion", "software"]),
                            declarada=rng.random() > 0.2,
                        ),
                        qos=1,
                    )
                await c.publish(
                    f"{base}/vuelta",
                    _json(equipo=equipo, numero=numero, t_inicio=t_inicio, t_fin=time.time()),
                    qos=1,
                )
                resumen[equipo] = numero
        finally:
            for t in tareas:
                t.cancel()


async def main(args: argparse.Namespace) -> None:
    rng = random.Random(args.semilla)
    resumen: dict[int, int] = {}
    estaciones_tarea = asyncio.create_task(estaciones(args, random.Random(rng.random())))
    carritos = [
        asyncio.create_task(carrito(args, n, random.Random(rng.random()), resumen))
        for n in range(1, args.carritos + 1)
    ]
    await asyncio.gather(*carritos)
    estaciones_tarea.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await estaciones_tarea
    print("vueltas cerradas por equipo:", dict(sorted(resumen.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--usuario", default=None)
    parser.add_argument("--carritos", type=int, default=10)
    parser.add_argument("--velocidad", type=float, default=20.0, help="compresión del tiempo")
    parser.add_argument("--prob-intervencion", type=float, default=0.15)
    parser.add_argument("--semilla", type=int, default=1)
    argumentos = parser.parse_args()
    # En Windows aiomqtt necesita el bucle Selector.
    factoria = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(argumentos), loop_factory=factoria)
