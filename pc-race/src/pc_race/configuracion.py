import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Configuracion:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_usuario: str = "racecontrol"
    mqtt_clave: str | None = None  # nunca en el código: viene de GRANPRIX_MQTT_CLAVE
    ledger: str = "ledger.sqlite3"
    consola: bool = True
    api_host: str = "127.0.0.1"  # 0.0.0.0 para que el juez entre desde otro equipo
    api_port: int = 8080
    api_token: str | None = None  # si se define, las acciones del juez lo exigen (X-Token)

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        env = os.environ
        return cls(
            mqtt_host=env.get("GRANPRIX_MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(env.get("GRANPRIX_MQTT_PORT", cls.mqtt_port)),
            mqtt_usuario=env.get("GRANPRIX_MQTT_USUARIO", cls.mqtt_usuario),
            mqtt_clave=env.get("GRANPRIX_MQTT_CLAVE"),
            ledger=env.get("GRANPRIX_LEDGER", cls.ledger),
            consola=env.get("GRANPRIX_CONSOLA", "1") != "0",
            api_host=env.get("GRANPRIX_API_HOST", cls.api_host),
            api_port=int(env.get("GRANPRIX_API_PORT", cls.api_port)),
            api_token=env.get("GRANPRIX_API_TOKEN"),
        )
