"""Unit tests for Overpass client (mocked)."""
from unittest.mock import patch, MagicMock
from app.overpass_client import fetch_pois


@patch("app.overpass_client.httpx.Client")
def test_fetch_pois(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "elements": [
            {
                "type": "node",
                "id": 123,
                "lat": 3.8480,
                "lon": 11.5021,
                "tags": {"name": "Pharmacie Centrale", "amenity": "pharmacy"},
            }
        ]
    }
    mock_client.return_value.__enter__.return_value.post.return_value = mock_response
    pois = fetch_pois("Yaoundé")
    assert len(pois) == 1
    assert pois[0]["place_id"] == "123"
    assert pois[0]["category"] == "pharmacy"
