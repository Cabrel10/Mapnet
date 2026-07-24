"""MapNet INFRASTRUCTURE — Repository in-memory avec snapshot JSON.

Implémente le port `CaptureRepository`. Garde les agrégats en mémoire (rapide,
sans dépendance externe) et peut sérialiser un instantané sur disque pour la
persistance légère et l'inspection. En production ce serait PostGIS/PostgreSQL,
mais l'abstraction permet de brancher n'importe quel backend.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional

from ..application.capture_service import CaptureRepository
from ..domain.entities import Capture


class InMemoryCaptureRepository(CaptureRepository):
    def __init__(self, snapshot_path: Optional[str] = None):
        self._store: Dict[str, Capture] = {}
        self._lock = threading.Lock()
        self.snapshot_path = snapshot_path

    def add(self, capture: Capture) -> None:
        with self._lock:
            self._store[capture.capture_id] = capture
        self._maybe_snapshot()

    def get(self, capture_id: str) -> Optional[Capture]:
        with self._lock:
            return self._store.get(capture_id)

    def list(self) -> List[Capture]:
        with self._lock:
            return list(self._store.values())

    def _maybe_snapshot(self) -> None:
        if not self.snapshot_path:
            return
        try:
            os.makedirs(os.path.dirname(self.snapshot_path) or ".", exist_ok=True)
            with self._lock:
                data = [c.to_dict() for c in self._store.values()]
            with open(self.snapshot_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def geojson(self) -> Dict:
        """Exporte les captures en FeatureCollection GeoJSON (pour Leaflet)."""
        features = []
        for c in self.list():
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [c.point.lon, c.point.lat]},
                "properties": {
                    "capture_id": c.capture_id,
                    "kind": c.kind,
                    "label": c.label,
                    "state": c.state.value,
                    "trust_score": round(c.trust_score, 3),
                    "flags": c.quality.flags if c.quality else [],
                },
            })
        return {"type": "FeatureCollection", "features": features}
