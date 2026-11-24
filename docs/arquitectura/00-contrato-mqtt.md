# Contrato MQTT

Es lo único que comparten las tres partes. Se versiona en el repositorio (`contrato/`) como modelos pydantic; de ahí salen los JSON Schema.

## Tópicos

| Tópico | Publica | Lee | QoS | Retenido | Contenido |
|---|---|---|---|---|---|
| `granprix/carrera/estado` | Race Control | todos | 1 | sí | tanda, fase |
| `granprix/carrera/bandera` | Race Control | todos | 1 | no | verde o roja |
| `granprix/estacion/<n>/turno` | Race Control | estación `n` | 1 | sí | equipo con el turno |
| `granprix/estacion/<n>/estado` | estación | todos | 1 | sí | `LIBRE`, `ESPERANDO`, `CAMBIANDO`, `LISTA`, `OFFLINE` |
| `granprix/estacion/<n>/solicitud` | carrito | estación `n` y Race Control | 1 | no | pose en el dock y pieza |
| `granprix/estacion/<n>/resultado` | estación | carrito y Race Control | 1 | no | ok, pieza, tiempo |
| `granprix/eqNN/turno` | Race Control | carrito NN | 1 | sí | autorizado o no |
| `granprix/eqNN/telemetria` | carrito | Race Control | 0 | no | pose, batería, velocidad, hasta 5 Hz |
| `granprix/eqNN/evento` | carrito | Race Control | 1 | no | intervención, pit ok, reintento |
| `granprix/eqNN/vuelta` | carrito | Race Control | 1 | no | número de vuelta y tiempos |

## Mensajes clave

```json
// carrito → granprix/estacion/2/solicitud
{ "v": 1, "ts": 1764001234.12, "equipo": 7, "dock": 2,
  "pose": {"dx": 0.021, "dy": -0.012, "dth": 1.8},
  "pieza_trae": "A" }

// estación → granprix/estacion/2/resultado
{ "v": 1, "ts": 1764001240.02, "equipo": 7, "ok": true,
  "pieza_dejo": "B", "t_cambio": 5.8 }

// carrito → granprix/eq07/evento
{ "v": 1, "ts": 1764001300.50, "equipo": 7, "tipo": "intervencion",
  "subtipo": "fisica", "declarada": true }
```

Unidades: metros para `dx` y `dy`, grados para `dth`, segundos para tiempos.

## Seguridad

| Cliente | Usuario | Puede escribir | Puede leer |
|---|---|---|---|
| Race Control | `racecontrol` | `granprix/carrera/#`, `granprix/estacion/+/turno`, `granprix/+/turno` | todo |
| Estación n | `estacionN` | `granprix/estacion/N/estado`, `/resultado` | `granprix/carrera/#`, `granprix/estacion/N/#` |
| Carrito NN | `carritoNN` | `granprix/eqNN/#`, `granprix/estacion/+/solicitud` | `granprix/carrera/#`, `granprix/eqNN/turno`, `granprix/estacion/+/estado`, `granprix/estacion/+/resultado` |

Todos usan Last Will: si un cliente cae, el broker publica `OFFLINE` en su estado.

## Reglas de compatibilidad

- Campo nuevo: se agrega como opcional y no sube `v`.
- Campo quitado o con otro significado: sube `v` y Race Control acepta las dos versiones durante una tanda de prueba.
- Un mensaje inválido se descarta y se cuenta; nunca detiene a Race Control.
