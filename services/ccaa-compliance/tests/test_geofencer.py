"""Unit tests for CCAA geofencer."""
from shapely.geometry import shape
from app.geofencer import check_flight_plan, load_nofly_zones_from_file


def test_conflict_in_airport():
    zones = load_nofly_zones_from_file()
    assert len(zones) > 0
    polygon = shape({
        "type": "Polygon",
        "coordinates": [[
            [11.5331, 3.8365],
            [11.5431, 3.8365],
            [11.5431, 3.8465],
            [11.5331, 3.8465],
            [11.5331, 3.8365],
        ]]
    })
    result = check_flight_plan(polygon, 50)
    assert result["status"] == "rejected"
    assert len(result["conflicts"]) > 0


def test_no_conflict_outside():
    polygon = shape({
        "type": "Polygon",
        "coordinates": [[
            [11.0, 3.0],
            [11.01, 3.0],
            [11.01, 3.01],
            [11.0, 3.01],
            [11.0, 3.0],
        ]]
    })
    result = check_flight_plan(polygon, 50)
    assert result["status"] == "approved"
