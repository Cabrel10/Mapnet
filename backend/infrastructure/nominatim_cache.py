"""Reverse-geocoding Nominatim avec cache local thread-safe."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class NominatimCache:
    def __init__(self, cache_path: Optional[str] = None, ttl_s: float = 30 * 86400):
        self.cache_path = cache_path
        self.ttl_s = ttl_s
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        # Environ 110 m : assez précis pour un quartier et réutilisable.
        return f"{lat:.3f},{lon:.3f}"

    def get_neighborhood(self, lat: float, lon: float) -> Optional[str]:
        key = self._key(lat, lon)
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - float(cached.get("cached_at", 0)) < self.ttl_s:
                return cached.get("neighborhood")
        neighborhood = self._reverse(lat, lon)
        with self._lock:
            self._cache[key] = {"neighborhood": neighborhood, "cached_at": now}
            self._save()
        return neighborhood

    def _reverse(self, lat: float, lon: float) -> Optional[str]:
        query = urlencode({
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 15,
            "addressdetails": 1,
        })
        base = os.environ.get(
            "MAPNET_NOMINATIM_URL", "https://nominatim.openstreetmap.org/reverse"
        )
        request = Request(
            f"{base}?{query}",
            headers={
                "User-Agent": os.environ.get(
                    "MAPNET_NOMINATIM_USER_AGENT", "MapNet/2.0 contact=admin@mapnet.local"
                ),
                "Accept-Language": "fr",
            },
        )
        try:
            with urlopen(request, timeout=3.0) as response:  # nosec B310: URL configurable by operator
                payload = json.loads(response.read().decode("utf-8"))
            address = payload.get("address") or {}
            for field in ("neighbourhood", "suburb", "quarter", "city_district", "city"):
                value = address.get(field)
                if value:
                    return str(value)
        except Exception:
            return None
        return None

    def _load(self) -> None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                self._cache = payload
        except (OSError, ValueError):
            self._cache = {}

    def _save(self) -> None:
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            temp_path = f"{self.cache_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self._cache, handle, ensure_ascii=False)
            os.replace(temp_path, self.cache_path)
        except OSError:
            pass
