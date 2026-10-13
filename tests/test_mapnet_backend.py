"""Tests des fonctions opérationnelles documentées de MapNet."""
from pathlib import Path

from backend.application.capture_service import CaptureService
from backend.application.device_service import DeviceService
from backend.application.event_bus import EventBus
from backend.infrastructure.memory_repo import InMemoryCaptureRepository
from backend.infrastructure.nominatim_cache import NominatimCache


class FakeGeocoder:
    def __init__(self):
        self.calls = 0

    def get_neighborhood(self, lat, lon):
        self.calls += 1
        return "Bastos"


def make_capture_service():
    repo = InMemoryCaptureRepository()
    geocoder = FakeGeocoder()
    return CaptureService(repo, EventBus(), geocoder=geocoder), repo, geocoder


def test_capture_creation_is_idempotent_by_client_capture_id():
    service, repo, geocoder = make_capture_service()
    first = service.create_capture(
        3.848,
        11.5021,
        kind="poi",
        label="Terrain",
        capture_id="mobile-001",
        signals={"accuracy_m": 4.5},
    )
    second = service.create_capture(
        0,
        0,
        kind="gps",
        capture_id="mobile-001",
    )

    assert first is second
    assert len(repo.list()) == 1
    assert first.metadata["neighborhood"] == "Bastos"
    assert geocoder.calls == 1


def test_sync_capture_is_idempotent_and_persisted():
    service, repo, _ = make_capture_service()
    capture = service.create_capture(
        3.848, 11.5021, capture_id="sync-001", signals={"neighborhood": "Mokolo"}
    )
    first = service.sync_capture(capture.capture_id)
    second = service.sync_capture(capture.capture_id)

    assert first is second
    assert first.state.value == "SERVER_CONFIRMED"
    assert repo.get(capture.capture_id).state.value == "SERVER_CONFIRMED"


def test_device_heartbeat_tracks_online_and_offline_sessions():
    devices = DeviceService(online_timeout_s=60)
    session = devices.heartbeat(
        {
            "device_id": "phone-001",
            "session_id": "session-a",
            "name": "Agent Bastos",
            "lat": 3.87,
            "lon": 11.51,
            "accuracy_m": 5.0,
            "sensors": {"heading": 92.0, "steps": 12},
        },
        now=1000,
    )

    assert session.sensor_snapshot["steps"] == 12
    assert devices.list_devices(now=1059)[0]["is_online"] is True
    assert devices.list_devices(now=1061)[0]["is_online"] is False

    feature = devices.geojson(now=1059)["features"][0]
    assert feature["properties"]["feature_type"] == "device"
    assert feature["geometry"]["coordinates"] == [11.51, 3.87]


def test_capture_geojson_contains_neighborhood_and_feature_type():
    service, repo, _ = make_capture_service()
    service.create_capture(
        3.848,
        11.5021,
        capture_id="geo-001",
        signals={"neighborhood": "Mvog-Mbi"},
    )
    feature = repo.geojson()["features"][0]
    assert feature["properties"]["feature_type"] == "capture"
    assert feature["properties"]["neighborhood"] == "Mvog-Mbi"


def test_nominatim_cache_persists_and_avoids_duplicate_reverse_lookup():
    cache_path = Path(__file__).parent / ".nominatim_cache_test.json"

    class CountingGeocoder(NominatimCache):
        calls = 0

        def _reverse(self, lat, lon):
            self.calls += 1
            return "EBOGO CITY"

    try:
        first = CountingGeocoder(cache_path=str(cache_path))
        assert first.get_neighborhood(3.848, 11.5021) == "EBOGO CITY"
        assert first.calls == 1

        reloaded = CountingGeocoder(cache_path=str(cache_path))
        assert reloaded.get_neighborhood(3.848, 11.5021) == "EBOGO CITY"
        assert reloaded.calls == 0
    finally:
        cache_path.unlink(missing_ok=True)
