"""Qualité MapNet calculée uniquement depuis des mesures physiques disponibles."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _rounded(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


@dataclass
class QualitySignals:
    """Mesures réelles. ``None`` signifie indisponible, jamais une valeur mockée."""

    accuracy_m: Optional[float] = None
    satellites: Optional[int] = None
    hdop: Optional[float] = None
    imu_consistency: Optional[float] = None
    speed_ms: Optional[float] = None
    prev_speed_ms: Optional[float] = None
    dt_s: Optional[float] = None
    sensor_confidence: Optional[float] = None


@dataclass
class QualityReport:
    gps_score: Optional[float]
    signal_score: Optional[float]
    imu_score: Optional[float]
    spoofing_score: Optional[float]
    confidence_score: Optional[float]
    trust_score: float
    flags: List[str] = field(default_factory=list)
    available_metrics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "gps_score": _rounded(self.gps_score),
            "signal_score": _rounded(self.signal_score),
            "imu_score": _rounded(self.imu_score),
            "spoofing_score": _rounded(self.spoofing_score),
            "confidence_score": _rounded(self.confidence_score),
            "trust_score": round(self.trust_score, 4),
            "flags": self.flags,
            "available_metrics": self.available_metrics,
            "metrics_are_physical": True,
        }


class QualityPipeline:
    """Fusion pondérée qui renormalise uniquement les métriques disponibles."""

    WEIGHTS = {
        "gps": 0.30,
        "signal": 0.20,
        "imu": 0.20,
        "spoofing": 0.20,
        "confidence": 0.10,
    }

    def _gps(self, signals: QualitySignals) -> Optional[float]:
        if signals.accuracy_m is None:
            return None
        return _clip01(1.0 - (signals.accuracy_m / 50.0))

    def _signal(self, signals: QualitySignals) -> Optional[float]:
        if signals.satellites is None or signals.hdop is None:
            return None
        satellites = _clip01(signals.satellites / 12.0)
        hdop = _clip01(1.0 - (signals.hdop - 1.0) / 5.0)
        return _clip01(0.6 * satellites + 0.4 * hdop)

    def _imu(self, signals: QualitySignals) -> Optional[float]:
        if signals.imu_consistency is None:
            return None
        return _clip01(signals.imu_consistency)

    def _spoofing(self, signals: QualitySignals) -> Optional[float]:
        if (
            signals.speed_ms is None
            or signals.prev_speed_ms is None
            or signals.dt_s is None
        ):
            return None
        dt = max(1e-3, signals.dt_s)
        acceleration = abs(signals.speed_ms - signals.prev_speed_ms) / dt
        return _clip01(1.0 - (acceleration / 30.0))

    def _confidence(self, signals: QualitySignals) -> Optional[float]:
        if signals.sensor_confidence is None:
            return None
        return _clip01(signals.sensor_confidence)

    def evaluate(self, signals: QualitySignals) -> QualityReport:
        scores = {
            "gps": self._gps(signals),
            "signal": self._signal(signals),
            "imu": self._imu(signals),
            "spoofing": self._spoofing(signals),
            "confidence": self._confidence(signals),
        }
        available = [name for name, value in scores.items() if value is not None]
        denominator = sum(self.WEIGHTS[name] for name in available)
        trust = (
            sum(self.WEIGHTS[name] * float(scores[name]) for name in available)
            / denominator
            if denominator
            else 0.0
        )
        flags: List[str] = []
        if not available:
            flags.append("NO_REAL_SENSOR_DATA")
        if scores["gps"] is None:
            flags.append("GPS_UNAVAILABLE")
        elif scores["gps"] < 0.4:
            flags.append("LOW_GPS_ACCURACY")
        if scores["signal"] is None:
            flags.append("SATELLITE_METRICS_UNAVAILABLE")
        elif scores["signal"] < 0.4:
            flags.append("WEAK_SIGNAL")
        if scores["imu"] is None:
            flags.append("IMU_UNAVAILABLE")
        if scores["spoofing"] is not None and scores["spoofing"] < 0.5:
            flags.append("POSSIBLE_SPOOFING")
        if trust < 0.5:
            flags.append("NEEDS_REVIEW")
        return QualityReport(
            gps_score=scores["gps"],
            signal_score=scores["signal"],
            imu_score=scores["imu"],
            spoofing_score=scores["spoofing"],
            confidence_score=scores["confidence"],
            trust_score=_clip01(trust),
            flags=flags,
            available_metrics=available,
        )
