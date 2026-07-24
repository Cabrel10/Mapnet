"""MapNet APPLICATION — Service de capture (use cases).

Orchestre le cycle complet d'une capture :
  1. Création de l'agrégat Capture (domaine).
  2. Évaluation qualité -> trust score (pipeline domaine).
  3. Émission des événements de domaine sur le bus.
  4. Progression de la machine à états (LOCAL -> ENCRYPTED -> ...).
  5. Persistance via un repository (couche infrastructure, injecté).

Ne connaît NI le web NI la base concrète : dépend d'abstractions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..domain.entities import Capture, GeoPoint
from ..domain.state_machine import CaptureState
from ..domain.quality import QualityPipeline, QualitySignals
from ..domain.events import (
    poi_created, road_condition_detected, voice_recorded,
    sync_requested, sync_completed, gateway_detected, mesh_peer_found,
)
from .event_bus import EventBus


class CaptureRepository:
    """Interface (port) de persistance des captures."""

    def add(self, capture: Capture) -> None: raise NotImplementedError
    def get(self, capture_id: str) -> Optional[Capture]: raise NotImplementedError
    def list(self) -> List[Capture]: raise NotImplementedError


class CaptureService:
    def __init__(self, repo: CaptureRepository, bus: EventBus,
                 pipeline: Optional[QualityPipeline] = None):
        self.repo = repo
        self.bus = bus
        self.pipeline = pipeline or QualityPipeline()

    def create_capture(self, lat: float, lon: float, kind: str = "gps",
                       label: str = "", signals: Optional[Dict[str, Any]] = None
                       ) -> Capture:
        s = signals or {}
        point = GeoPoint(lat=lat, lon=lon, accuracy_m=float(s.get("accuracy_m", 10.0)))
        cap = Capture(point=point, kind=kind, label=label,
                      metadata={"speed": s.get("speed", 0.0)})

        # 1) événement de type selon le kind
        if kind == "gps":
            cap.record_gps()
        elif kind == "poi":
            cap._pending_events.append(poi_created(cap.capture_id, label, "poi", lat, lon))
        elif kind == "road_condition":
            cap._pending_events.append(
                road_condition_detected(cap.capture_id, label or "bump",
                                        float(s.get("severity", 0.5))))
        elif kind == "voice":
            cap._pending_events.append(
                voice_recorded(cap.capture_id, float(s.get("duration_s", 3.0)),
                               s.get("transcript", "")))
        else:
            cap.record_gps()

        # 2) qualité -> trust
        qsig = QualitySignals(
            accuracy_m=float(s.get("accuracy_m", 10.0)),
            satellites=int(s.get("satellites", 8)),
            hdop=float(s.get("hdop", 1.5)),
            imu_consistency=float(s.get("imu_consistency", 0.9)),
            speed_ms=float(s.get("speed", 0.0)),
            prev_speed_ms=float(s.get("prev_speed", 0.0)),
            dt_s=float(s.get("dt_s", 1.0)),
            sensor_confidence=float(s.get("sensor_confidence", 0.8)),
        )
        cap.set_quality(self.pipeline.evaluate(qsig))

        # 3) machine à états : NEW -> LOCAL -> ENCRYPTED
        cap.advance(CaptureState.LOCAL)
        cap.advance(CaptureState.ENCRYPTED)

        # 4) publie les événements de domaine
        self.bus.publish_many(cap.collect_events())

        # 5) persiste
        self.repo.add(cap)
        return cap

    def sync_capture(self, capture_id: str, via_mesh: bool = False) -> Optional[Capture]:
        """Fait progresser une capture vers le serveur (mesh optionnel)."""
        cap = self.repo.get(capture_id)
        if cap is None:
            return None
        self.bus.publish(sync_requested(cap.capture_id, "server"))
        if via_mesh and cap.can_advance_mesh():
            cap.advance(CaptureState.MESH_SHARED)
            self.bus.publish(mesh_peer_found(cap.capture_id, "peer-001", hops=1))
        self.bus.publish(gateway_detected(cap.capture_id, "gw-eu-01", rssi=-62.0))
        cap.advance(CaptureState.GATEWAY_UPLOADED)
        cap.advance(CaptureState.SERVER_CONFIRMED)
        self.bus.publish(sync_completed(cap.capture_id, "server", bytes_sent=512))
        return cap

    def stats(self) -> Dict[str, Any]:
        caps = self.repo.list()
        by_state: Dict[str, int] = {}
        by_kind: Dict[str, int] = {}
        trust_sum = 0.0
        for c in caps:
            by_state[c.state.value] = by_state.get(c.state.value, 0) + 1
            by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
            trust_sum += c.trust_score
        n = max(1, len(caps))
        return {
            "total": len(caps),
            "by_state": by_state,
            "by_kind": by_kind,
            "avg_trust": round(trust_sum / n, 4),
            "events": self.bus.event_count,
        }
