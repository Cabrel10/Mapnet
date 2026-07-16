"""Unit tests for routing client (mocked)."""
import pytest
from unittest.mock import patch, MagicMock
from app.osrm_client import map_match, route


@patch("app.osrm_client.httpx.Client")
def test_map_match_ok(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "Ok", "matchings": [{"geometry": {}}]}
    mock_client.return_value.__enter__.return_value.get.return_value = mock_response
    data = map_match([{"latitude": 3.8480, "longitude": 11.5021}, {"latitude": 3.8481, "longitude": 11.5022}])
    assert data["code"] == "Ok"


@patch("app.osrm_client.httpx.Client")
def test_route_ok(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "Ok", "routes": [{"distance": 100}]}
    mock_client.return_value.__enter__.return_value.get.return_value = mock_response
    data = route(3.8480, 11.5021, 3.8481, 11.5022)
    assert data["code"] == "Ok"
