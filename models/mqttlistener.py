from __future__ import annotations
import dataclasses
from dataclasses import dataclass
from typing import Optional

import paho.mqtt.client as mqtt


@dataclass
class MqttListenerConfiguration:
    host: str
    port: int = 1883

    username: Optional[str] = None
    password: Optional[str] = None


class MqttListener:
    def __init__(
        self, host, port=1883, username: Optional[str] = None, password: Optional[str] = None
    ):
        self._mqtt = mqtt.Client()
        self._host = host
        self._port = port
        self._username = username
        self._password = password

        self._connect_listeners = []
        self._connect_fail_listeners = []
        self._disconnect_listeners = []
        self._message_listeners = []

        if username:
            self._mqtt.username_pw_set(self._username, self._password)

    @staticmethod
    def from_config(config: MqttListenerConfiguration) -> MqttListener:
        return MqttListener(**dataclasses.asdict(config))

    def to_config(self) -> dict:
        return {
            "host": self._host,
            "port": self._port,
            "username": self._username,
            "password": self._password,
        }

    def connect(self):
        self._mqtt.on_connect = self._connect_listener
        self._mqtt.on_message = self._message_listener
        self._mqtt.on_disconnect = self._disconnect_listener

        self._mqtt.connect_async(self._host, self._port)
        self._mqtt.loop_start()

    def disconnect(self):
        self._mqtt.disconnect()
        self._mqtt.loop_stop()

    def publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        self._mqtt.publish(topic, payload, qos, retain, properties)

    def add_connect_listener(self, connect_listener):
        self._connect_listeners.append(connect_listener)

    def add_connect_fail_listener(self, connect_fail_listener):
        self._connect_fail_listeners.append(connect_fail_listener)

    def add_disconnect_listener(self, disconnect_listener):
        self._disconnect_listeners.append(disconnect_listener)

    def add_message_listener(self, message_listener):
        self._message_listeners.append(message_listener)

    def _connect_listener(self, client: mqtt.Client, userdata, flags, rc):
        if rc != 0:  # Connection failed
            for listener in self._connect_fail_listeners:
                listener(client)
            return

        client.subscribe("#")  # Subscribe to all topics
        for listener in self._connect_listeners:  # Notify all other listeners
            listener(client, userdata, flags, rc)

    def _disconnect_listener(self, *args):
        for listener in self._disconnect_listeners:  # Notify all other listeners
            listener(*args)

    def _message_listener(self, *args):
        for listener in self._message_listeners:  # Notify all other listeners
            listener(*args)