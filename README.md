# GranPrix Delivery Semiautónomo

Reto de robótica: carritos semiautónomos que hacen una vuelta pasando por cuatro estaciones con un brazo JetCobot, donde cambian una pieza (el *pit*). Una computadora de Race Control arbitra la carrera: lleva la tanda, valida las vueltas, cuenta las intervenciones y calcula el ranking.

Entre máquinas solo hay MQTT, HTTP y SSH; ROS 2 vive dentro de cada una.

| Carpeta | Qué es |
|---|---|
| [`pc-race/`](pc-race/README.md) | Race Control, el programa del curso que arbitra la carrera (Python, MQTT) |
| [`estacion/`](estacion/README.md) | Código de la estación del JetCobot; por ahora, la herramienta de AprilTag |
| [`docs/arquitectura/`](docs/arquitectura/README.md) | Arquitectura de los tres desarrollos y el contrato MQTT |

El carrito MicroROS-Pi5 (documento `03-microros-pi5-carrito.md`) todavía no tiene código en este repositorio.
