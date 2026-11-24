# estacion · JetCobot

Código de la computadora de la estación (direcciones `.21` a `.24`). Según [`docs/arquitectura/02-jetcobot-estacion.md`](../docs/arquitectura/02-jetcobot-estacion.md) son dos programas con dueños distintos: el `supervisor_estacion` (curso), que habla con Race Control y el carrito y congela el brazo, y la `app_equipo` (equipo), que decide cómo hacer el cambio de pieza.

## Estado

Por ahora esta carpeta solo tiene herramientas de laboratorio. El supervisor y la plantilla del equipo todavía no están escritos.

| Pieza | Estado |
|---|---|
| `supervisor/` (supervisor de la estación) | Pendiente |
| `plantilla_equipo/` (plantilla de `app_equipo`) | Pendiente |
| `herramientas/` (AprilTag) | Hecho |

El control del JetCobot (librería, puerto, latencia) sigue por confirmar con el hardware real; solo cambiará el adaptador `brazo_jetcobot.py`.

## Herramientas

### `herramientas/herramienta_apriltag.py`

Crea y detecta AprilTags. Es de laboratorio: no es parte del supervisor, no toca el brazo y no cambia la decisión de que el brazo no use cámara.

| Comando | Qué hace |
|---|---|
| `crear --id 3 --tamano-mm 60` | Escribe el tag en PNG y en SVG a tamaño real para imprimir al 100 % |
| `detectar --camara 0` | Lee de cámara (o de `--imagen`, o de `--video`) y escribe una línea JSON por tag |
| `detectar ... --tamano-mm 60 --fov-h 70` | Además da la pose: `x`, `y`, `z` en metros y `dth` en grados |
| `autoprueba` | Crea tags, los pone en una imagen y comprueba que se leen con el mismo id |

Familias: `tag36h11` (por defecto), `tag25h9` y `tag16h5`. La pose necesita el lado real del tag impreso y la cámara; con `--fov-h` es una aproximación sin distorsión, y con `--fx --fy --cx --cy` de una calibración sale mejor.

Imágenes de ejemplo, con la entrada y la salida de cada comando, en [`herramientas/ejemplos/`](herramientas/ejemplos/README.md).

#### Instalación

```
cd estacion/herramientas
python -m venv .venv
.venv\Scripts\activate          # en Linux: source .venv/bin/activate
pip install -r requirements.txt
```

En la Jetson del JetCobot OpenCV suele venir con JetPack: instala solo lo que falte.

#### Pruebas

```
cd estacion/herramientas
pytest
```

Las pruebas no usan cámara: crean los tags, los dibujan (incluso en perspectiva, girados) y comprueban que se leen con el mismo id, la distancia y el giro correctos.

#### Lo que falta probar

- **Cámara real.** El camino `--camara` usa `cv2.VideoCapture`; en una Jetson con cámara CSI puede hacer falta pasar un pipeline de GStreamer en `--camara`. Solo se probó con imágenes y video.
- **Medidas reales.** Con una cámara de verdad y un tag impreso, comparar `z` con una regla.
