"""MapNet DOMAIN — Événements (Event-Driven Architecture).

Chaque changement significatif du système émet un événement immuable. Les
handlers (couche application) réagissent sans couplage direct. C'est la
colonne vertébrale event-driven du cahier des charges MapNet.

Événements du cycle de vie d'une capture géospatiale :
    GPSCaptured, RoadConditionDetected, POICreated, VoiceRecorded,
    SyncRequested, SyncCompleted, GatewayDetected, MeshPeerFound.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DomainEvent:
    """Événement de domaine immuable et horodaté."""
    event_type: str
    aggregate_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Fabriques typées (documentent le contrat de chaque événement) ------- #
def gps_captured(aggregate_id: str, lat: float, lon: float, accuracy_m: float,
                 speed: Optional[float] = None) -> DomainEvent:
    return DomainEvent("GPSCaptured", aggregate_id,
                       {"lat": lat, "lon": lon, "accuracy_m": accuracy_m, "speed": speed})


def road_condition_detected(aggregate_id: str, condition: str, severity: float) -> DomainEvent:
    return DomainEvent("RoadConditionDetected", aggregate_id,
                       {"condition": condition, "severity": severity})


def poi_created(aggregate_id: str, name: str, category: str,
                lat: float, lon: float) -> DomainEvent:
    return DomainEvent("POICreated", aggregate_id,
                       {"name": name, "category": category, "lat": lat, "lon": lon})


def voice_recorded(aggregate_id: str, duration_s: float, transcript: str = "") -> DomainEvent:
    return DomainEvent("VoiceRecorded", aggregate_id,
                       {"duration_s": duration_s, "transcript": transcript})


def sync_requested(aggregate_id: str, target: str) -> DomainEvent:
    return DomainEvent("SyncRequested", aggregate_id, {"target": target})


def sync_completed(aggregate_id: str, target: str, bytes_sent: int) -> DomainEvent:
    return DomainEvent("SyncCompleted", aggregate_id,
                       {"target": target, "bytes_sent": bytes_sent})


def gateway_detected(aggregate_id: str, gateway_id: str, rssi: float) -> DomainEvent:
    return DomainEvent("GatewayDetected", aggregate_id,
                       {"gateway_id": gateway_id, "rssi": rssi})


def mesh_peer_found(aggregate_id: str, peer_id: str, hops: int) -> DomainEvent:
    return DomainEvent("MeshPeerFound", aggregate_id,
                       {"peer_id": peer_id, "hops": hops})


# Registre des types d'événements connus (validation / documentation).
KNOWN_EVENT_TYPES = {
    "GPSCaptured", "RoadConditionDetected", "POICreated", "VoiceRecorded",
    "SyncRequested", "SyncCompleted", "GatewayDetected", "MeshPeerFound",
    "CaptureStateChanged",
}
