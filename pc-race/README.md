# pc-race · Race Control

Programa del curso que arbitra la carrera del **GranPrix Delivery Semiautónomo**. Corre en un solo proceso asyncio (Python 3.12 o superior). Recibe lo que publican los carritos y las estaciones por MQTT, lleva la tanda, valida las vueltas, cuenta las intervenciones y calcula el ranking. **No mueve robots**: el algoritmo es del equipo, el curso solo arbitra.

La arquitectura completa está en [`docs/arquitectura/`](../docs/arquitectura/): el contrato entre las tres partes en `00-contrato-mqtt.md` y el diseño de este programa en `01-pc-race.md`.

## Estado

| Paso | Qué es | Estado |
|---|---|---|
| 1 | Dominio y pruebas (tanda, vuelta, pit, intervención, ranking) | Hecho |
| 2 | Ledger SQLite y casos de uso | Hecho |
| 3 | `MqttGateway`, `PublicadorMqtt` y simulador de carritos | Hecho |
| 4 | `ApiWeb` y tablero del juez | Hecho |
| 5 | `DespliegueSsh` | Solo diseño: [`04-despliegue-ssh.md`](../docs/arquitectura/04-despliegue-ssh.md) |

Pendiente: probarlo con Mosquitto y la seguridad por usuarios (hoy solo se probó con un broker de Python, anónimo), medir la latencia con 10 carritos, y definir quién asigna el turno de cada estación.

## Requisitos

- Python 3.12 o superior.
- Un broker MQTT, por ejemplo Mosquitto, al que Race Control se conecta como cliente.

## Instalación

```
cd pc-race
python -m venv .venv
.venv\Scripts\activate          # en Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

## Ejecución

```
pc-race
```

(o `python -m pc_race.main`). Se configura con variables de entorno; la clave del broker **nunca** va en el código.

| Variable | Qué es | Por defecto |
|---|---|---|
| `GRANPRIX_MQTT_HOST` | Dirección del broker | `localhost` |
| `GRANPRIX_MQTT_PORT` | Puerto del broker | `1883` |
| `GRANPRIX_MQTT_USUARIO` | Usuario MQTT | `racecontrol` |
| `GRANPRIX_MQTT_CLAVE` | Clave MQTT | sin clave |
| `GRANPRIX_LEDGER` | Archivo SQLite del ledger | `ledger.sqlite3` |
| `GRANPRIX_API_HOST` | Dirección donde escucha el tablero | `127.0.0.1` |
| `GRANPRIX_API_PORT` | Puerto del tablero | `8080` |
| `GRANPRIX_API_TOKEN` | Si se define, las acciones del juez exigen la cabecera `X-Token` | sin token |
| `GRANPRIX_CONSOLA` | `0` desactiva la consola del juez por teclado | activa |

Si el broker no está disponible, Race Control reintenta con espera creciente (1 s hasta 30 s) y sigue sirviendo el tablero. Al reiniciar, reconstruye la tanda desde el ledger y vuelve a publicar los estados retenidos.

Para que el juez entre desde otra computadora hay que poner `GRANPRIX_API_HOST=0.0.0.0`; en ese caso define también `GRANPRIX_API_TOKEN`, porque cualquiera en la red podría dar órdenes.

### Tablero del juez

`http://127.0.0.1:8080/`: ranking, fase y cronómetro de la tanda, avisos (estaciones o carritos `OFFLINE`), mensajes descartados y los controles del juez. Se actualiza por WebSocket.

| Ruta | Qué hace |
|---|---|
| `GET /api/estado` | Estado completo (el mismo que recibe el WebSocket) |
| `POST /api/tanda` | Crea la tanda: `{"equipos": [1, 2, 3], "con_calentamiento": true}` |
| `POST /api/carrera` | Pasa a carrera |
| `POST /api/bandera/roja`, `POST /api/bandera/verde` | Bandera |
| `POST /api/intervencion` | Intervención vista por el juez: `{"equipo": 7, "tipo": "fisica", "declarada": false}` |
| `POST /api/fin` | Termina la tanda |
| `WS /ws` | Estado en vivo |

La documentación interactiva de la API está en `/api/docs`.

### Consola del juez

Respaldo por teclado: `tanda 1 2 3`, `carrera`, `roja`, `verde`, `fin`, `int <equipo> <tipo>`, `ranking`, `estado`, `ayuda`.

## Pruebas

```
pytest                                      # dominio, aplicación, contrato y adaptadores
ruff check src contrato tests
mypy src contrato                           # modo estricto
```

Con un broker real, el simulador lanza carritos y estaciones falsos:

```
python simulador_carritos.py --host localhost --carritos 10 --velocidad 20
```

`--velocidad` comprime el tiempo. Si el broker pide clave, va en `GRANPRIX_MQTT_CLAVE`. Para ver el resultado, crea una tanda con los mismos equipos (`1` a `N`) desde el tablero y pasa a carrera.

Los JSON Schema del contrato salen de los modelos: `python -m contrato.esquemas`.

## Estructura

```
src/pc_race/
  dominio/          reglas puras: tanda, vuelta, pit, intervención, ranking, bandera
  aplicacion/       casos de uso y puertos
  adaptadores/
    entrada/        mqtt_gateway, api_web (+ tablero.html), consola_juez
    salida/         publicador_mqtt, ledger_sqlite, tablero_memoria, reloj
  configuracion.py
  main.py           arma todo y arranca
contrato/           modelos pydantic del contrato MQTT
tests/
simulador_carritos.py
```

El dominio no importa MQTT, HTTP ni SQLite: eso son adaptadores.

## Reglas que se asumieron

Los documentos no las fijan del todo. Si el reglamento dice otra cosa, cada una se cambia en un solo lugar.

- Una intervención no declarada que ve el juez suma 1 + 3 puntos (`dominio/intervencion.py`).
- La bandera roja detiene el cronómetro de carrera (`dominio/tanda.py`).
- El error de pose para el desempate usa solo la distancia `dx`, `dy`, sin `dth`.
- El mensaje `vuelta` puede traer `estaciones`; si no, el recorrido se infiere de los pits.
- Las estaciones y los carritos se marcan `OFFLINE` si pasan más de 3 s sin publicar.
