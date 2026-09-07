"""MapNet APPLICATION — Système de Plugins de capteurs.

Chaque capteur est un plugin déclarant ses capacités. Le registre permet
d'activer/désactiver dynamiquement des sources et d'interroger celles
disponibles. Capteurs du cahier des charges :

    GPS, Camera, IMU, Microphone, Bluetooth, WiFi Aware, Barometer.

Un plugin expose `read()` -> dict de signaux. Ici on fournit des plugins
"stub" déterministes (le vrai matériel est côté mobile) : suffisant pour la
démo web + les tests d'architecture.
"""
from __future__ import annotations

import random
from typing import Dict, List, Protocol


class SensorPlugin(Protocol):
    name: str
    enabled: bool

    def capabilities(self) -> List[str]: ...
    def read(self) -> Dict: ...


class _BasePlugin:
    name: str = "base"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def capabilities(self) -> List[str]:
        return []

    def read(self) -> Dict:
        return {}


class GPSPlugin(_BasePlugin):
    name = "gps"

    def capabilities(self):
        return ["lat", "lon", "accuracy_m", "speed"]

    def read(self):
        return {"accuracy_m": round(random.uniform(3, 15), 1),
                "satellites": random.randint(6, 12)}


class CameraPlugin(_BasePlugin):
    name = "camera"

    def capabilities(self):
        return ["frame", "resolution"]

    def read(self):
        return {"resolution": "1920x1080"}


class IMUPlugin(_BasePlugin):
    name = "imu"

    def capabilities(self):
        return ["accel", "gyro", "consistency"]

    def read(self):
        return {"imu_consistency": round(random.uniform(0.7, 1.0), 3)}


class MicrophonePlugin(_BasePlugin):
    name = "microphone"

    def capabilities(self):
        return ["audio", "duration_s"]

    def read(self):
        return {"level_db": round(random.uniform(-60, -20), 1)}


class BluetoothPlugin(_BasePlugin):
    name = "bluetooth"

    def capabilities(self):
        return ["peers", "rssi"]

    def read(self):
        return {"peers": random.randint(0, 4)}


class WiFiAwarePlugin(_BasePlugin):
    name = "wifi_aware"

    def capabilities(self):
        return ["mesh_peers", "hops"]

    def read(self):
        return {"mesh_peers": random.randint(0, 3)}


class BarometerPlugin(_BasePlugin):
    name = "barometer"

    def capabilities(self):
        return ["pressure_hpa", "altitude_m"]

    def read(self):
        return {"pressure_hpa": round(random.uniform(990, 1030), 1)}


class PluginRegistry:
    """Registre central des plugins de capteurs."""

    def __init__(self) -> None:
        self._plugins: Dict[str, _BasePlugin] = {}
        for p in (GPSPlugin(), CameraPlugin(), IMUPlugin(), MicrophonePlugin(),
                  BluetoothPlugin(), WiFiAwarePlugin(), BarometerPlugin()):
            self.register(p)

    def register(self, plugin: _BasePlugin) -> None:
        self._plugins[plugin.name] = plugin

    def enable(self, name: str, enabled: bool = True) -> None:
        if name in self._plugins:
            self._plugins[name].enabled = enabled

    def get(self, name: str) -> _BasePlugin | None:
        return self._plugins.get(name)

    def snapshot(self) -> List[Dict]:
        return [
            {"name": p.name, "enabled": p.enabled, "capabilities": p.capabilities()}
            for p in self._plugins.values()
        ]
