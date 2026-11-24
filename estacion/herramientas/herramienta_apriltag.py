#!/usr/bin/env python3
"""Herramienta de AprilTag para la estación: crear el tag y detectarlo.

    python herramienta_apriltag.py crear --id 3 --tamano-mm 60 --salida tags/
    python herramienta_apriltag.py detectar --camara 0 --tamano-mm 60 --fov-h 70
    python herramienta_apriltag.py detectar --imagen foto.png --anotada salida.png
    python herramienta_apriltag.py autoprueba

`crear` escribe un PNG y un SVG. El SVG tiene el tamaño real en milímetros: imprímelo al
100 % (sin "ajustar a la página") y el lado negro del tag mide exactamente `--tamano-mm`.

`detectar` imprime una línea JSON por tag detectado. Sin parámetros de cámara solo da el id y
las esquinas; con `--tamano-mm` y la cámara (`--fov-h`, o `--fx --fy --cx --cy`) también da la
pose del tag respecto a la cámara.

Pose, en el sistema de la cámara (x a la derecha, y hacia abajo, z hacia adelante):
    x, y, z    metros, centro del tag
    dth        grados; giro del tag alrededor del eje vertical de la cámara (0 = de frente)
    error      error de reproyección que informa el detector

Es una herramienta de laboratorio: no forma parte del supervisor ni toca el brazo.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# familia -> (diccionario de OpenCV, celdas por lado incluyendo el borde negro)
FAMILIAS: dict[str, tuple[int, int]] = {
    "tag36h11": (cv2.aruco.DICT_APRILTAG_36h11, 8),
    "tag25h9": (cv2.aruco.DICT_APRILTAG_25h9, 7),
    "tag16h5": (cv2.aruco.DICT_APRILTAG_16h5, 6),
}
FAMILIA_POR_DEFECTO = "tag36h11"
MARGEN_CELDAS = 2  # borde blanco alrededor del tag; el detector lo necesita


class ErrorHerramienta(Exception):
    """Error de uso que se muestra sin traza."""


# --------------------------------------------------------------------------- crear


def ids_validos(familia: str) -> int:
    """Cantidad de ids que tiene la familia (0 .. n-1)."""
    dic = cv2.aruco.getPredefinedDictionary(FAMILIAS[familia][0])
    return int(dic.bytesList.shape[0])


def matriz_tag(familia: str, tag_id: int) -> np.ndarray:
    """Cuadrícula del tag: 1 = celda negra, 0 = blanca. Incluye el borde negro."""
    if familia not in FAMILIAS:
        raise ErrorHerramienta(f"familia desconocida: {familia} (usa {', '.join(FAMILIAS)})")
    total = ids_validos(familia)
    if not 0 <= tag_id < total:
        raise ErrorHerramienta(f"el id {tag_id} no existe en {familia}: va de 0 a {total - 1}")
    codigo, celdas = FAMILIAS[familia]
    dic = cv2.aruco.getPredefinedDictionary(codigo)
    imagen = cv2.aruco.generateImageMarker(dic, tag_id, celdas)
    return (imagen < 128).astype(np.uint8)


def imagen_png(familia: str, tag_id: int, px_celda: int = 40) -> np.ndarray:
    """Imagen en gris con el tag y su margen blanco. `px_celda` píxeles por celda."""
    celdas = matriz_tag(familia, tag_id)
    grande = np.kron(1 - celdas, np.ones((px_celda, px_celda), np.uint8)) * 255
    m = MARGEN_CELDAS * px_celda
    return np.pad(grande, m, constant_values=255).astype(np.uint8)


def svg_tag(familia: str, tag_id: int, tamano_mm: float) -> str:
    """SVG a tamaño real: el cuadrado negro exterior mide `tamano_mm`."""
    celdas = matriz_tag(familia, tag_id)
    n = celdas.shape[0]
    lado_total = n + 2 * MARGEN_CELDAS
    mm_total = tamano_mm * lado_total / n
    rects = []
    for fila in range(n):
        columna = 0
        while columna < n:  # junta las celdas negras contiguas en un solo rectángulo
            if celdas[fila, columna]:
                inicio = columna
                while columna < n and celdas[fila, columna]:
                    columna += 1
                rects.append(
                    f'<rect x="{inicio + MARGEN_CELDAS}" y="{fila + MARGEN_CELDAS}" '
                    f'width="{columna - inicio}" height="1"/>'
                )
            else:
                columna += 1
    cuerpo = "\n  ".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{mm_total:.3f}mm" '
        f'height="{mm_total:.3f}mm" viewBox="0 0 {lado_total} {lado_total}" '
        f'shape-rendering="crispEdges">\n'
        f'  <rect width="{lado_total}" height="{lado_total}" fill="#fff"/>\n'
        f'  <g fill="#000">\n  {cuerpo}\n  </g>\n</svg>\n'
    )


def guardar_png(ruta: Path, imagen: np.ndarray) -> None:
    ok, buffer = cv2.imencode(".png", imagen)
    if not ok:
        raise ErrorHerramienta(f"no se pudo codificar {ruta}")
    buffer.tofile(str(ruta))


def cmd_crear(args: argparse.Namespace) -> int:
    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    ids = _expandir_ids(args.id)
    for tag_id in ids:
        base = destino / f"{args.familia}_id{tag_id:03d}"
        png, svg = base.with_suffix(".png"), base.with_suffix(".svg")
        guardar_png(png, imagen_png(args.familia, tag_id, args.px_celda))
        svg.write_text(svg_tag(args.familia, tag_id, args.tamano_mm), encoding="utf-8")
        print(f"{args.familia} id {tag_id}: {png} y {svg}")
    print(
        f"Imprime el SVG al 100 %: el cuadrado negro debe medir {args.tamano_mm:g} mm. "
        "Mídelo con regla antes de usarlo para medir distancias."
    )
    return 0


def _expandir_ids(texto: str) -> list[int]:
    """'3' -> [3]; '0-4' -> [0..4]; '1,5,9' -> [1, 5, 9]."""
    ids: list[int] = []
    try:
        for parte in texto.split(","):
            if "-" in parte:
                a, b = parte.split("-")
                ids.extend(range(int(a), int(b) + 1))
            else:
                ids.append(int(parte))
    except ValueError:
        raise ErrorHerramienta(f"ids mal escritos: {texto!r} (ejemplos: 3, 0-4, 1,5,9)") from None
    return ids


# ------------------------------------------------------------------------- detectar


def crear_detector(familia: str, hilos: int = 2, decimacion: float = 1.0) -> Any:
    from pupil_apriltags import Detector  # import tardío: crear no lo necesita

    if familia not in FAMILIAS:
        raise ErrorHerramienta(f"familia desconocida: {familia}")
    return Detector(families=familia, nthreads=hilos, quad_decimate=decimacion)


def parametros_camara(
    ancho: int,
    alto: int,
    fx: float | None = None,
    fy: float | None = None,
    cx: float | None = None,
    cy: float | None = None,
    fov_h: float | None = None,
) -> tuple[float, float, float, float] | None:
    """(fx, fy, cx, cy) en píxeles. Prefiere los valores explícitos; si no, los saca del
    campo de visión horizontal (aproximado: sin distorsión). None si no hay datos."""
    if fx is not None:
        return (
            fx,
            fy if fy is not None else fx,
            cx if cx is not None else ancho / 2,
            cy if cy is not None else alto / 2,
        )
    if fov_h is not None:
        if not 0 < fov_h < 180:
            raise ErrorHerramienta("--fov-h debe estar entre 0 y 180 grados")
        f = (ancho / 2) / math.tan(math.radians(fov_h) / 2)
        return (f, f, ancho / 2, alto / 2)
    return None


def detectar_en(
    detector: Any,
    imagen: np.ndarray,
    params: tuple[float, float, float, float] | None = None,
    tamano_m: float | None = None,
) -> list[dict[str, Any]]:
    """Detecta los tags de una imagen (BGR o gris). Una entrada por tag."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    con_pose = params is not None and tamano_m is not None
    crudas = detector.detect(
        gris,
        estimate_tag_pose=con_pose,
        camera_params=params if con_pose else None,
        tag_size=tamano_m if con_pose else None,
    )
    salida = []
    for d in crudas:
        entrada: dict[str, Any] = {
            "id": int(d.tag_id),
            "centro": [round(float(v), 2) for v in d.center],
            "esquinas": [[round(float(x), 2), round(float(y), 2)] for x, y in d.corners],
            "margen": round(float(d.decision_margin), 1),
            "hamming": int(d.hamming),
            "pose": None,
        }
        if con_pose and d.pose_t is not None:
            r = np.asarray(d.pose_R)
            t = np.asarray(d.pose_t).reshape(3)
            entrada["pose"] = {
                "x": round(float(t[0]), 4),
                "y": round(float(t[1]), 4),
                "z": round(float(t[2]), 4),
                "dth": round(math.degrees(math.atan2(r[0, 2], r[2, 2])), 2),
                "error": float(d.pose_err),
            }
        salida.append(entrada)
    return salida


def anotar(imagen: np.ndarray, detecciones: list[dict[str, Any]]) -> np.ndarray:
    lienzo = cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR) if imagen.ndim == 2 else imagen.copy()
    for d in detecciones:
        puntos = np.array(d["esquinas"], np.int32).reshape(-1, 1, 2)
        cv2.polylines(lienzo, [puntos], True, (0, 255, 0), 2)
        lineas = [f"id {d['id']}"]
        if d["pose"]:
            lineas.append(f"z {d['pose']['z'] * 100:.1f} cm")
            lineas.append(f"dth {d['pose']['dth']:.1f} deg")
        # El texto va fuera del tag (arriba, o abajo si no cabe) para no tapar las celdas.
        x_min, y_min = np.min(d["esquinas"], axis=0)
        y_max = np.max(np.array(d["esquinas"])[:, 1])
        paso = 22
        arriba = y_min - 10 - paso * (len(lineas) - 1) >= 16
        for i, linea in enumerate(lineas):
            y = y_min - 10 - paso * (len(lineas) - 1 - i) if arriba else y_max + 22 + paso * i
            cv2.putText(
                lienzo, linea, (int(x_min), int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 255), 2, cv2.LINE_AA,
            )
    return lienzo


def leer_imagen(ruta: Path) -> np.ndarray:
    if not ruta.is_file():
        raise ErrorHerramienta(f"no existe la imagen: {ruta}")
    imagen = cv2.imdecode(np.fromfile(str(ruta), np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ErrorHerramienta(f"no se pudo leer {ruta} como imagen")
    return imagen


def fotogramas(args: argparse.Namespace) -> Iterator[np.ndarray]:
    """Fotogramas de la fuente elegida: imagen, video o cámara."""
    if args.imagen:
        yield leer_imagen(Path(args.imagen))
        return

    if args.video:
        if not Path(args.video).is_file():
            raise ErrorHerramienta(f"no existe el video: {args.video}")
        captura = cv2.VideoCapture(args.video)
    else:
        # número = índice de la cámara; texto = ruta (/dev/video0) o pipeline de GStreamer
        origen: int | str = int(args.camara) if str(args.camara).isdigit() else args.camara
        captura = cv2.VideoCapture(origen)
        if args.ancho:
            captura.set(cv2.CAP_PROP_FRAME_WIDTH, args.ancho)
        if args.alto:
            captura.set(cv2.CAP_PROP_FRAME_HEIGHT, args.alto)
    if not captura.isOpened():
        raise ErrorHerramienta(
            f"no se pudo abrir la fuente de video ({args.video or args.camara}). "
            "¿Otro programa usa la cámara? ¿El índice es el correcto?"
        )
    try:
        while True:
            ok, cuadro = captura.read()
            if not ok:
                return
            yield cuadro
    finally:
        captura.release()


def cmd_detectar(args: argparse.Namespace) -> int:
    detector = crear_detector(args.familia, args.hilos, args.decimacion)
    tamano_m = args.tamano_mm / 1000 if args.tamano_mm else None
    params: tuple[float, float, float, float] | None = None
    total = 0
    t0 = time.time()
    ultima: np.ndarray | None = None

    for numero, cuadro in enumerate(fotogramas(args), start=1):
        if params is None and tamano_m is not None:
            alto, ancho = cuadro.shape[:2]
            params = parametros_camara(ancho, alto, args.fx, args.fy, args.cx, args.cy, args.fov_h)
            if params is None:
                print(
                    "aviso: sin datos de la cámara (--fov-h o --fx) no se calcula la pose",
                    file=sys.stderr,
                )
                tamano_m = None
        detecciones = detectar_en(detector, cuadro, params, tamano_m)
        for d in detecciones:
            print(json.dumps({"cuadro": numero, "ts": round(time.time(), 3), **d}), flush=True)
        total += len(detecciones)
        ultima = anotar(cuadro, detecciones)

        if args.mostrar:
            cv2.imshow("apriltag (q para salir)", ultima)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if args.max_cuadros and numero >= args.max_cuadros:
            break
        if args.segundos and time.time() - t0 >= args.segundos:
            break

    if args.anotada and ultima is not None:
        guardar_png(Path(args.anotada), ultima)
        print(f"imagen anotada: {args.anotada}", file=sys.stderr)
    if args.mostrar:
        cv2.destroyAllWindows()
    print(f"{total} detecciones", file=sys.stderr)
    return 0 if total else 2  # 2 = no se vio ningún tag (útil en scripts)


# ------------------------------------------------------------------------ autoprueba


def componer_escena(familia: str, ids: list[int], px_celda: int = 12) -> np.ndarray:
    """Imagen sintética con los tags en fila sobre fondo gris claro."""
    tags = [imagen_png(familia, i, px_celda) for i in ids]
    alto = max(t.shape[0] for t in tags) + 60
    ancho = sum(t.shape[1] for t in tags) + 60 * (len(tags) + 1)
    escena = np.full((alto, ancho), 200, np.uint8)
    x = 60
    for t in tags:
        escena[30 : 30 + t.shape[0], x : x + t.shape[1]] = t
        x += t.shape[1] + 60
    return escena


def cmd_autoprueba(args: argparse.Namespace) -> int:
    """Crea tags, los pone en una imagen y comprueba que el detector lee los mismos ids."""
    ids = [i for i in (0, 1, 7, 12) if i < ids_validos(args.familia)]
    escena = componer_escena(args.familia, ids)
    detector = crear_detector(args.familia)
    detecciones = detectar_en(detector, escena)
    leidos = sorted(d["id"] for d in detecciones)
    if args.guardar:
        guardar_png(Path(args.guardar), anotar(escena, detecciones))
    esperado = sorted(ids)
    if leidos == esperado:
        print(f"OK: creados {esperado}, leídos {leidos} ({args.familia})")
        return 0
    print(f"FALLA: creados {esperado}, leídos {leidos} ({args.familia})", file=sys.stderr)
    return 1


# ------------------------------------------------------------------------------ main


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("crear", help="genera el tag en PNG y SVG a tamaño real")
    c.add_argument("--id", default="0", help="id, rango (0-4) o lista (1,5,9)")
    c.add_argument("--familia", default=FAMILIA_POR_DEFECTO, choices=FAMILIAS)
    c.add_argument("--tamano-mm", type=float, default=60.0, help="lado del cuadrado negro")
    c.add_argument("--px-celda", type=int, default=40, help="píxeles por celda en el PNG")
    c.add_argument("--salida", default="tags", help="carpeta de salida")
    c.set_defaults(funcion=cmd_crear)

    d = sub.add_parser("detectar", help="lee tags de cámara, imagen o video")
    fuente = d.add_mutually_exclusive_group()
    fuente.add_argument("--camara", default="0", help="índice, ruta o pipeline GStreamer")
    fuente.add_argument("--imagen", help="archivo de imagen")
    fuente.add_argument("--video", help="archivo de video")
    d.add_argument("--ancho", type=int, help="ancho pedido a la cámara")
    d.add_argument("--alto", type=int, help="alto pedido a la cámara")
    d.add_argument("--familia", default=FAMILIA_POR_DEFECTO, choices=FAMILIAS)
    d.add_argument("--tamano-mm", type=float, help="lado del cuadrado negro; activa la pose")
    d.add_argument("--fov-h", type=float, help="campo de visión horizontal en grados (aprox.)")
    d.add_argument("--fx", type=float)
    d.add_argument("--fy", type=float)
    d.add_argument("--cx", type=float)
    d.add_argument("--cy", type=float)
    d.add_argument("--hilos", type=int, default=2)
    d.add_argument("--decimacion", type=float, default=1.0, help=">1 = más rápido, menos alcance")
    d.add_argument("--max-cuadros", type=int, help="termina tras N cuadros")
    d.add_argument("--segundos", type=float, help="termina tras N segundos")
    d.add_argument("--mostrar", action="store_true", help="abre una ventana (necesita pantalla)")
    d.add_argument("--anotada", help="guarda el último cuadro anotado en este PNG")
    d.set_defaults(funcion=cmd_detectar)

    a = sub.add_parser("autoprueba", help="crea tags y comprueba que se leen")
    a.add_argument("--familia", default=FAMILIA_POR_DEFECTO, choices=FAMILIAS)
    a.add_argument("--guardar", help="guarda la escena anotada para verla")
    a.set_defaults(funcion=cmd_autoprueba)
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return int(args.funcion(args))
    except ErrorHerramienta as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
