# Despliegue por SSH · Paso 5 de Race Control

Estado: **diseño, sin código**. Los pasos 1 a 4 de `01-pc-race.md` están implementados en `pc-race/`. Este documento define qué hará el paso 5 y deja anotado lo que falta decidir antes de programarlo.

## Qué resuelve

Cada equipo programa su `app_equipo` (la estrategia de cambio de pieza). Esa app corre en la computadora de la estación, no en el PC de Race Control. Race Control la lleva hasta allá por SSH, así nadie copia archivos a mano entre tandas.

Lo que dicen los documentos hoy, y nada más:

> Race Control copia el código del equipo a `/opt/granprix/app_equipo` por SSH en el cambio de tanda y reinicia el servicio `app-equipo` con systemd. El supervisor no se reemplaza. (`02-jetcobot-estacion.md`)

## Pregunta abierta que bloquea el diseño

Una estación tiene **un solo** directorio `/opt/granprix/app_equipo`, pero una tanda puede tener hasta 10 equipos y hay 4 estaciones. El carrito de cualquier equipo puede pedir pit en cualquier estación. Hay tres lecturas posibles:

| Opción | Cómo funcionaría | Qué implica |
|---|---|---|
| A. Un equipo por estación y por tanda | Cada estación se carga con el código de un solo equipo | Una tanda tiene como máximo 4 equipos |
| B. Todas las apps en cada estación | `/opt/granprix/equipos/eqNN/` para cada equipo; el supervisor elige según el turno | Se despliega una vez por tanda; hay que definir cómo el supervisor carga la app del equipo con el turno |
| C. Se redespliega en cada turno | Race Control copia y reinicia cada vez que cambia el equipo de una estación | Cientos de reinicios por carrera; cada uno cuesta segundos con el carrito esperando |

La opción B es la que menos choca con el resto: no cambia el contrato y encaja con `granprix/estacion/<n>/turno`. Pero **depende de otro hueco**: ningún documento dice quién decide qué equipo tiene el turno en cada estación (ver `00-contrato-mqtt.md`, tópico `turno`). Las dos preguntas se resuelven juntas.

El resto de este documento asume la opción B, y lo marca donde importa.

## Responsabilidades

| Pieza | Dueño | Qué hace |
|---|---|---|
| `DespliegueEstaciones` (puerto) | Curso | Interfaz que ve la aplicación: desplegar un equipo en una estación y devolver el resultado |
| `DespliegueSsh` (adaptador) | Curso | Implementa el puerto con `asyncssh`. Es lo único que conoce SSH |
| `PrepararEstaciones` (caso de uso) | Curso | Decide cuándo y en qué estaciones desplegar, y avisa al juez |
| `supervisor_estacion` | Curso | No se toca. Ya está corriendo en la estación |
| Código del equipo | Equipo | Una carpeta por equipo en el PC de Race Control |

## Cuándo se despliega

Solo con la carrera detenida: tanda en `PENDIENTE` o `FIN`. Con la tanda en `CALENTAMIENTO`, `CARRERA` o `ROJA` se rechaza. Así un reinicio de servicio nunca pasa con un carrito en pista.

1. El juez pulsa **Desplegar equipos** en el tablero (o llama a `POST /api/despliegue`) con la lista de equipos de la próxima tanda.
2. Race Control despliega en las 4 estaciones a la vez.
3. Cuando las 4 salen bien, crear la tanda queda habilitado. Si alguna falla, el tablero lo dice y el juez decide (reintentar, o forzar y asumir que esa estación queda sin el código nuevo).

## Pasos por estación

| # | Paso | Falla si |
|---|---|---|
| 1 | Revisa que la estación no esté `OFFLINE` en el monitor de latidos | lleva más de 3 s sin latido |
| 2 | Abre la conexión SSH con clave y verifica la huella del servidor | la huella no coincide con `known_hosts` |
| 3 | Copia `eqNN/` a `/opt/granprix/equipos/eqNN.nuevo/` por SFTP | corte de red, disco lleno |
| 4 | Compara `sha256` de cada archivo contra el manifiesto calculado en el PC | algún archivo no coincide |
| 5 | Mueve `eqNN` a `eqNN.anterior` y `eqNN.nuevo` a `eqNN` | el movimiento falla |
| 6 | `sudo systemctl restart app-equipo` | el comando devuelve error |
| 7 | Espera que la estación publique `estado` `LIBRE` o `ESPERANDO` | no llega en 15 s (plazo a definir) |

Si el paso 6 o el 7 falla, se vuelve a `eqNN.anterior` y se reinicia el servicio. El resultado de cada estación es uno de: `ok`, `ok_con_reversion`, `fallo`, con el motivo.

Los pasos 3 a 5 se hacen sobre una carpeta nueva y se cambian de golpe, así una copia cortada nunca deja la estación con medio código.

## Seguridad

Lo que sigue es una **propuesta**: ningún documento lo fija todavía.

| Riesgo | Medida |
|---|---|
| Un equipo toca el supervisor o el brazo | La app corre con un usuario sin permisos sobre `/opt/granprix/supervisor` ni sobre la clave del broker. El supervisor es el único con acceso al brazo (regla de `02`) |
| Suplantar una estación | Se verifica la huella SSH contra un `known_hosts` fijo. No se acepta ninguna huella desconocida |
| Robo de la clave de despliegue | Solo clave SSH, sin contraseña. La ruta de la clave viene de una variable de entorno y la clave nunca va en el repositorio |
| Un usuario de despliegue con demasiado poder | Usuario `granprix-deploy`, dueño de `/opt/granprix/equipos` y con permiso `sudo` solo para `systemctl restart app-equipo` |
| Código del equipo que no es el suyo | El manifiesto lleva `sha256` por archivo y se verifica en la estación (paso 4) |

## Configuración

Variables de entorno de Race Control, en la misma línea que las existentes (`GRANPRIX_MQTT_*`, `GRANPRIX_API_*`):

| Variable | Qué es |
|---|---|
| `GRANPRIX_DESPLIEGUE_USUARIO` | Usuario SSH de las estaciones (por defecto `granprix-deploy`) |
| `GRANPRIX_DESPLIEGUE_CLAVE` | Ruta al archivo de la clave privada |
| `GRANPRIX_DESPLIEGUE_KNOWN_HOSTS` | Ruta al `known_hosts` con las 4 huellas |
| `GRANPRIX_EQUIPOS_DIR` | Carpeta del PC con una subcarpeta `eqNN/` por equipo |
| `GRANPRIX_ESTACIONES` | Direcciones de las estaciones, de la 1 a la 4 |

Las estaciones están en las direcciones `.21` a `.24`. El broker está en `192.168.50.10` según `03`, así que la red sería `192.168.50.0/24`, pero **hay que confirmarlo**.

## Dónde encaja en el código

Sigue la estructura de `01-pc-race.md`: el puerto en la aplicación y SSH solo en el adaptador.

```
aplicacion/puertos.py                      DespliegueEstaciones (Protocol)
aplicacion/casos_de_uso/preparar_estaciones.py
adaptadores/salida/despliegue_ssh.py       DespliegueSsh (asyncssh)
adaptadores/entrada/api_web.py             POST /api/despliegue
```

Forma propuesta del puerto:

```python
class DespliegueEstaciones(Protocol):
    async def desplegar(self, estacion: int, equipo: int) -> ResultadoDespliegue: ...
```

`ResultadoDespliegue` lleva `estacion`, `equipo`, `estado` (`ok`, `ok_con_reversion`, `fallo`) y `motivo`.

## Fallos y qué hace

| Fallo | Respuesta |
|---|---|
| Estación `OFFLINE` | No se intenta. Se avisa al juez y esa estación cuenta como fallo |
| SSH no conecta o la huella no coincide | Un reintento a los 2 s. Si falla, `fallo` con el motivo |
| Copia incompleta o `sha256` distinto | La carpeta `.nuevo` se borra. La estación sigue con su código anterior |
| El servicio no arranca o la estación no vuelve a `LIBRE` | Reversión a `.anterior` y nuevo reinicio |
| Fallo en 1 de 4 estaciones | Las otras tres siguen. El juez ve cuál falló |
| Despliegue pedido con la carrera en marcha | Se rechaza con `409` |
| Reinicio de Race Control a mitad del despliegue | No hay estado que reconstruir: el juez repite el despliegue, que es idempotente |

## Pruebas

- **Dominio y aplicación:** `PrepararEstaciones` con un `DespliegueEstaciones` falso. Se prueba la regla de fase, el fallo parcial y el aviso al juez. No hay red.
- **Adaptador:** `asyncssh` puede levantar un servidor SSH dentro del propio test. Se prueban huella incorrecta, copia cortada y `sha256` distinto sin tocar una estación real. En Windows no hay `sshd` a mano, así que esto es lo que permite probarlo.
- **Estación real:** una prueba con una estación antes de la carrera: desplegar, ver el servicio activo, forzar un fallo de arranque y comprobar la reversión.

## Por confirmar

- Si se usa la opción A, B o C (ver arriba) y quién asigna el turno en cada estación.
- Cómo `supervisor_estacion` elige la app del equipo con el turno si se adopta B.
- Red y direcciones exactas de las estaciones, y el sistema operativo de su computadora (el despliegue asume Linux con systemd, como dice `02`).
- Plazo del paso 7 y tamaño esperado del código de un equipo.
- Quién crea el usuario `granprix-deploy` y las reglas de `sudo` en cada estación.
