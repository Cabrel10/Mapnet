"""MapNet DOMAIN — Pipeline de Qualité -> Global Trust Score.

Chaque capture passe par une chaîne de contrôles qualité indépendants, dont
les scores [0..1] sont fusionnés (sensor fusion) en un TRUST SCORE global :

    GPS quality   -> précision positionnelle (accuracy_m, HDOP)
    Signal quality-> force du signal / satellites visibles
    IMU quality   -> cohérence accéléro/gyro (mouvement plausible)
    Spoofing check-> détection d'incohérences (vitesse/saut impossibles)
    Confidence    -> confiance déclarée par le capteur
    Sensor fusion -> combinaison pondérée -> Global Trust Score

Le trust score module l'acceptation d'une donnée côté serveur : une capture
au trust faible est marquée "à vérifier" plutôt que rejetée.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass
class QualitySignals:
    """Signaux bruts fournis par les capteurs pour une capture."""
    accuracy_m: float = 10.0        # précision GPS en mètres (plus bas = mieux)
    satellites: int = 8             # nombre de satellites visibles
    hdop: float = 1.5               # dilution horizontale de précision
    imu_consistency: float = 0.9    # cohérence accéléro/gyro [0..1]
    speed_ms: float = 0.0           # vitesse instantanée m/s
    prev_speed_ms: float = 0.0      # vitesse au pas précédent m/s
    dt_s: float = 1.0               # intervalle entre deux mesures
    sensor_confidence: float = 0.8  # confiance déclarée par le capteur [0..1]


@dataclass
class QualityReport:
    gps_score: float
    signal_score: float
    imu_score: float
    spoofing_score: float
    confidence_score: float
    trust_score: float
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "gps_score": round(self.gps_score, 4),
            "signal_score": round(self.signal_score, 4),
            "imu_score": round(self.imu_score, 4),
            "spoofing_score": round(self.spoofing_score, 4),
            "confidence_score": round(self.confidence_score, 4),
            "trust_score": round(self.trust_score, 4),
            "flags": self.flags,
        }


class QualityPipeline:
    """Chaîne de contrôles qualité + fusion en Global Trust Score."""

    # Pondérations de la fusion (somme = 1.0).
    WEIGHTS = {
        "gps": 0.30, "signal": 0.20, "imu": 0.20,
        "spoofing": 0.20, "confidence": 0.10,
    }

    def _gps(self, s: QualitySignals) -> float:
        # 0m -> 1.0 ; 50m -> ~0.0. Décroissance linéaire bornée.
        return _clip01(1.0 - (s.accuracy_m / 50.0))

    def _signal(self, s: QualitySignals) -> float:
        sat = _clip01(s.satellites / 12.0)
        hdop = _clip01(1.0 - (s.hdop - 1.0) / 5.0)  # hdop 1 -> 1.0 ; 6 -> 0.0
        return _clip01(0.6 * sat + 0.4 * hdop)

    def _imu(self, s: QualitySignals) -> float:
        return _clip01(s.imu_consistency)

    def _spoofing(self, s: QualitySignals) -> float:
        """Détecte sauts de vitesse physiquement impossibles.

        Accélération > 15 m/s^2 (~1.5g) soutenue = suspect (spoofing/glitch).
        Retourne un score [0..1] : 1 = plausible, 0 = très suspect.
        """
        dt = max(1e-3, s.dt_s)
        accel = abs(s.speed_ms - s.prev_speed_ms) / dt
        return _clip01(1.0 - (accel / 30.0))  # 0 m/s^2 -> 1.0 ; 30 -> 0.0

    def _confidence(self, s: QualitySignals) -> float:
        return _clip01(s.sensor_confidence)

    def evaluate(self, s: QualitySignals) -> QualityReport:
        gps = self._gps(s)
        signal = self._signal(s)
        imu = self._imu(s)
        spoof = self._spoofing(s)
        conf = self._confidence(s)
        w = self.WEIGHTS
        trust = (w["gps"] * gps + w["signal"] * signal + w["imu"] * imu +
                 w["spoofing"] * spoof + w["confidence"] * conf)
        flags: List[str] = []
        if gps < 0.4:
            flags.append("LOW_GPS_ACCURACY")
        if spoof < 0.5:
            flags.append("POSSIBLE_SPOOFING")
        if signal < 0.4:
            flags.append("WEAK_SIGNAL")
        if trust < 0.5:
            flags.append("NEEDS_REVIEW")
        return QualityReport(gps, signal, imu, spoof, conf, _clip01(trust), flags)
