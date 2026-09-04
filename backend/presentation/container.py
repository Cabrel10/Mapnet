"""MapNet PRESENTATION — Composition Root de production.

Câble les couches DDD, les projections, le registre des appareils et le
reverse-geocoding. Aucune donnée terrain synthétique n'est créée.
"""
from __future__ import annotations

import os

from ..application.event_bus import EventBus
from ..application.plugins import PluginRegistry
from ..application.capture_service import CaptureService
from ..application.device_service import DeviceService
from ..infrastructure.memory_repo import InMemoryCaptureRepository
from ..infrastructure.nominatim_cache import NominatimCache


class Container:
    def __init__(self, snapshot_path: str | None = None):
        self.bus = EventBus()
        self.plugins = PluginRegistry()
        self.repo = InMemoryCaptureRepository(snapshot_path=snapshot_path)
        cache_path = os.path.join(os.path.dirname(snapshot_path), "nominatim_cache.json") if snapshot_path else None
        self.geocoder = NominatimCache(cache_path=cache_path)
        self.devices = DeviceService()
        self.service = CaptureService(self.repo, self.bus, geocoder=self.geocoder)
        self._wire_projections()

    def _wire_projections(self) -> None:
        # Exemple de handler event-driven : journalise chaque sync complétée.
        def on_sync_completed(evt):
            # (dans un vrai système : notifier, mettre à jour une projection…)
            pass
        self.bus.subscribe("SyncCompleted", on_sync_completed)
