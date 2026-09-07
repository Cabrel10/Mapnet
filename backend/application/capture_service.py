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

import math
import uuid
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
    def save(self, capture: Capture) -> None: raise NotImplementedError
    def get(self, capture_id: str) -> Optional[Capture]: raise NotImplementedError
    def list(self) -> List[Capture]: raise NotImplementedError


class CaptureService:
    def __init__(self, repo: CaptureRepository, bus: EventBus,
                 pipeline: Optional[QualityPipeline] = None, geocoder=None):
        self.repo = repo
        self.bus = bus
        self.pipeline = pipeline or QualityPipeline()
        self.geocoder = geocoder

    def create_capture(self, lat: float, lon: float, kind: str = "gps",
                       label: str = "", signals: Optional[Dict[str, Any]] = None,
                       capture_id: Optional[str] = None) -> Capture:
        """Crée une capture de façon idempotente par ``capture_id``."""
        if capture_id:
            existing = self.repo.get(capture_id)
            if existing is not None:
                return existing
        s = signals or {}
        accuracy = _optional_float(s.get("accuracy_m"))
        point = GeoPoint(
            lat=lat,
            lon=lon,
            accuracy_m=accuracy if accuracy is not None else 0.0,
        )
        neighborhood = s.get("neighborhood")
        if not neighborhood and self.geocoder is not None:
            neighborhood = self.geocoder.get_neighborhood(lat, lon)
        metadata = dict(s)
        if neighborhood:
            metadata["neighborhood"] = neighborhood
        cap = Capture(
            point=point,
            kind=kind,
            label=label,
            capture_id=capture_id or uuid.uuid4().hex,
            metadata=metadata,
        )

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
        imu_consistency = _optional_float(s.get("imu_consistency"))
        if imu_consistency is None:
            imu_consistency = _imu_consistency_from_sensors(s.get("sensors"))
        qsig = QualitySignals(
            accuracy_m=accuracy,
            satellites=_optional_int(s.get("satellites")),
            hdop=_optional_float(s.get("hdop")),
            imu_consistency=imu_consistency,
            speed_ms=_optional_float(s.get("speed")),
            prev_speed_ms=_optional_float(s.get("prev_speed")),
            dt_s=_optional_float(s.get("dt_s")),
            sensor_confidence=_optional_float(s.get("sensor_confidence")),
        )
        metadata["quality_signal_sources"] = {
            "accuracy_m": "gps_sensor" if accuracy is not None else None,
            "satellites": "gps_sensor" if qsig.satellites is not None else None,
            "hdop": "gps_sensor" if qsig.hdop is not None else None,
            "imu_consistency": "physical_imu" if imu_consistency is not None else None,
            "speed": "gps_sensor" if qsig.speed_ms is not None else None,
        }
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
        if cap.state in (CaptureState.SERVER_CONFIRMED, CaptureState.ARCHIVED):
            return cap
        self.bus.publish(sync_requested(cap.capture_id, "server"))
        if via_mesh and cap.can_advance_mesh():
            cap.advance(CaptureState.MESH_SHARED)
            self.bus.publish(mesh_peer_found(cap.capture_id, "peer-001", hops=1))
        self.bus.publish(gateway_detected(cap.capture_id, "gw-eu-01", rssi=-62.0))
        cap.advance(CaptureState.GATEWAY_UPLOADED)
        cap.advance(CaptureState.SERVER_CONFIRMED)
        self.repo.save(cap)
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
            "metrics_source": "physical_capture_signals_only",
        }


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_int(value: Any) -> Optional[int]:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def _imu_consistency_from_sensors(value: Any) -> Optional[float]:
    if not isinstance(value, dict):
        return None
    accelerometer = value.get("accelerometer_ms2")
    gyroscope = value.get("gyroscope_rads")
    if not isinstance(accelerometer, dict):
        return None
    axes = [_optional_float(accelerometer.get(axis)) for axis in ("x", "y", "z")]
    if any(axis is None for axis in axes):
        return None
    magnitude = math.sqrt(sum(float(axis) ** 2 for axis in axes))
    gravity_plausibility = max(0.0, 1.0 - abs(magnitude - 9.80665) / 9.80665)
    if not isinstance(gyroscope, dict):
        return gravity_plausibility
    gyro_axes = [_optional_float(gyroscope.get(axis)) for axis in ("x", "y", "z")]
    if any(axis is None for axis in gyro_axes):
        return gravity_plausibility
    gyro_magnitude = math.sqrt(sum(float(axis) ** 2 for axis in gyro_axes))
    gyro_plausibility = max(0.0, 1.0 - gyro_magnitude / 20.0)
    return 0.7 * gravity_plausibility + 0.3 * gyro_plausibility
