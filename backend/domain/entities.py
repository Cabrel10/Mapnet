"""MapNet DOMAIN — Entités & Value Objects + Schema Versioning.

L'agrégat racine est `Capture` : une observation géospatiale terrain qui
possède un état (machine à états), un trust score (pipeline qualité) et une
liste d'événements de domaine non encore publiés.

Schema Versioning : chaque capture porte un `schema_version`. Le module
`schema.py` gère la migration V1 -> V2 et le rollback.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .state_machine import CaptureState, CaptureStateMachine
from .quality import QualityReport
from .events import DomainEvent, gps_captured


SCHEMA_VERSION = 2  # version courante du schéma de capture


@dataclass
class Device:
    """Terminal terrain connu du serveur."""

    device_id: str
    name: str = "Agent MapNet"
    platform: str = "android"
    app_version: str = "unknown"
    registered_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "platform": self.platform,
            "app_version": self.app_version,
            "registered_at": self.registered_at,
            "metadata": self.metadata,
        }


@dataclass
class DeviceSession:
    """Session vivante, rafraîchie par les heartbeats du mobile."""

    device_id: str
    session_id: str
    started_at: float = field(default_factory=time.time)
    last_heartbeat_at: float = field(default_factory=time.time)
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    accuracy_m: Optional[float] = None
    sensor_snapshot: Dict[str, Any] = field(default_factory=dict)

    def is_online(self, now: Optional[float] = None, timeout_s: float = 90.0) -> bool:
        return (now if now is not None else time.time()) - self.last_heartbeat_at <= timeout_s

    def to_dict(self, now: Optional[float] = None, timeout_s: float = 90.0) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "location_lat": self.location_lat,
            "location_lon": self.location_lon,
            "accuracy_m": self.accuracy_m,
            "sensor_snapshot": self.sensor_snapshot,
            "is_online": self.is_online(now=now, timeout_s=timeout_s),
        }


@dataclass
class GeoPoint:
    """Value object : un point géographique."""
    lat: float
    lon: float
    accuracy_m: float = 10.0

    def to_dict(self) -> Dict[str, Any]:
        return {"lat": self.lat, "lon": self.lon, "accuracy_m": self.accuracy_m}


@dataclass
class Capture:
    """Agrégat racine : une capture géospatiale terrain."""
    point: GeoPoint
    kind: str = "gps"  # gps | poi | road_condition | voice
    label: str = ""
    schema_version: int = SCHEMA_VERSION
    capture_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _sm: CaptureStateMachine = field(default_factory=CaptureStateMachine)
    quality: Optional[QualityReport] = None
    _pending_events: List[DomainEvent] = field(default_factory=list)

    # --- Comportements métier ------------------------------------------- #
    def record_gps(self) -> None:
        self._pending_events.append(
            gps_captured(self.capture_id, self.point.lat, self.point.lon,
                         self.point.accuracy_m,
                         speed=self.metadata.get("speed"))
        )

    def set_quality(self, report: QualityReport) -> None:
        self.quality = report

    @property
    def state(self) -> CaptureState:
        return self._sm.state

    def advance(self, target: CaptureState) -> None:
        self._sm.transition(target)

    def can_advance_mesh(self) -> bool:
        return self._sm.can_transition(CaptureState.MESH_SHARED)

    def collect_events(self) -> List[DomainEvent]:
        evts = list(self._pending_events)
        self._pending_events.clear()
        return evts

    @property
    def trust_score(self) -> float:
        return self.quality.trust_score if self.quality else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "kind": self.kind,
            "label": self.label,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "point": self.point.to_dict(),
            "state": self._sm.state.value,
            "state_history": [s.value for s in self._sm.history],
            "trust_score": round(self.trust_score, 4),
            "quality": self.quality.to_dict() if self.quality else None,
            "metadata": self.metadata,
            "neighborhood": self.metadata.get("neighborhood"),
        }
