"""Gestion des appareils terrain, sessions et heartbeats."""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..domain.entities import Device, DeviceSession


class DeviceService:
    """Registre thread-safe des appareils et de leur session active."""

    def __init__(self, online_timeout_s: Optional[float] = None):
        self.online_timeout_s = float(
            online_timeout_s
            if online_timeout_s is not None
            else os.environ.get("MAPNET_DEVICE_TIMEOUT_S", "90")
        )
        self._devices: Dict[str, Device] = {}
        self._sessions: Dict[Tuple[str, str], DeviceSession] = {}
        self._lock = threading.RLock()

    def heartbeat(self, payload: Dict[str, Any], now: Optional[float] = None) -> DeviceSession:
        device_id = str(payload.get("device_id", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        if not device_id or not session_id:
            raise ValueError("device_id and session_id are required")
        timestamp = float(now if now is not None else time.time())
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                device = Device(
                    device_id=device_id,
                    name=str(payload.get("name") or f"Agent {device_id[-6:]}"),
                    platform=str(payload.get("platform") or "android"),
                    app_version=str(payload.get("app_version") or "unknown"),
                    registered_at=timestamp,
                )
                self._devices[device_id] = device
            key = (device_id, session_id)
            session = self._sessions.get(key)
            if session is None:
                session = DeviceSession(
                    device_id=device_id,
                    session_id=session_id,
                    started_at=timestamp,
                    last_heartbeat_at=timestamp,
                )
                self._sessions[key] = session
            session.last_heartbeat_at = timestamp
            session.location_lat = _optional_float(payload.get("lat"))
            session.location_lon = _optional_float(payload.get("lon"))
            session.accuracy_m = _optional_float(payload.get("accuracy_m"))
            sensors = payload.get("sensors")
            session.sensor_snapshot = dict(sensors) if isinstance(sensors, dict) else {}
            return session

    def list_devices(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        timestamp = float(now if now is not None else time.time())
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for device in self._devices.values():
                sessions = [
                    session
                    for (device_id, _), session in self._sessions.items()
                    if device_id == device.device_id
                ]
                latest = max(sessions, key=lambda item: item.last_heartbeat_at, default=None)
                row = device.to_dict()
                row["session"] = (
                    latest.to_dict(timestamp, self.online_timeout_s) if latest else None
                )
                row["is_online"] = bool(
                    latest and latest.is_online(timestamp, self.online_timeout_s)
                )
                rows.append(row)
            return sorted(rows, key=lambda row: row["device_id"])

    def geojson(self, now: Optional[float] = None) -> Dict[str, Any]:
        features = []
        for row in self.list_devices(now=now):
            session = row.get("session") or {}
            lat, lon = session.get("location_lat"), session.get("location_lon")
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "feature_type": "device",
                    "device_id": row["device_id"],
                    "name": row["name"],
                    "session_id": session.get("session_id"),
                    "is_online": row["is_online"],
                    "last_heartbeat_at": session.get("last_heartbeat_at"),
                    "accuracy_m": session.get("accuracy_m"),
                    "sensors": session.get("sensor_snapshot", {}),
                },
            })
        return {"type": "FeatureCollection", "features": features}


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
