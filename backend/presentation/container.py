"""MapNet PRESENTATION — Composition Root.

Câble ensemble toutes les couches (DDD) et injecte quelques handlers
event-driven de démonstration. Fournit aussi un jeu de données initial pour
que la carte ne soit pas vide au démarrage.
"""
from __future__ import annotations

import os
import random

from ..application.event_bus import EventBus
from ..application.plugins import PluginRegistry
from ..application.capture_service import CaptureService
from ..infrastructure.memory_repo import InMemoryCaptureRepository
from ..domain.state_machine import CaptureState


class Container:
    def __init__(self, snapshot_path: str | None = None):
        self.bus = EventBus()
        self.plugins = PluginRegistry()
        self.repo = InMemoryCaptureRepository(snapshot_path=snapshot_path)
        self.service = CaptureService(self.repo, self.bus)
        self._wire_projections()

    def _wire_projections(self) -> None:
        # Exemple de handler event-driven : journalise chaque sync complétée.
        def on_sync_completed(evt):
            # (dans un vrai système : notifier, mettre à jour une projection…)
            pass
        self.bus.subscribe("SyncCompleted", on_sync_completed)

    def seed_demo(self, n: int = 25) -> None:
        """Sème des captures autour d'un centre (Ouagadougou par défaut)."""
        clat = float(os.environ.get("MAPNET_SEED_LAT", "12.3714"))
        clon = float(os.environ.get("MAPNET_SEED_LON", "-1.5197"))
        kinds = ["gps", "poi", "road_condition", "voice"]
        random.seed(42)
        for i in range(n):
            lat = clat + random.uniform(-0.05, 0.05)
            lon = clon + random.uniform(-0.05, 0.05)
            kind = random.choice(kinds)
            cap = self.service.create_capture(
                lat=lat, lon=lon, kind=kind,
                label=f"{kind}-{i}",
                signals={
                    "accuracy_m": random.uniform(3, 20),
                    "satellites": random.randint(5, 12),
                    "hdop": random.uniform(1.0, 4.0),
                    "imu_consistency": random.uniform(0.6, 1.0),
                    "speed": random.uniform(0, 15),
                    "prev_speed": random.uniform(0, 15),
                    "sensor_confidence": random.uniform(0.6, 0.95),
                },
            )
            # une partie des captures est déjà synchronisée (états variés)
            if i % 3 == 0:
                self.service.sync_capture(cap.capture_id, via_mesh=(i % 2 == 0))
