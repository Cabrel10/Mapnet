"""Integration tests for the MAPNET pipeline (no external brokers required)."""
import json
import os
import sys
import uuid
import importlib.util
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gps_collect_parser = _load_module(
    "gps_collect_parser",
    os.path.join(BASE_DIR, "services", "gps-collect", "app", "parser.py"),
)
map_engine_consumer = _load_module(
    "map_engine_consumer",
    os.path.join(BASE_DIR, "services", "map-engine", "app", "consumer.py"),
)

parse_gpx = gps_collect_parser.parse_gpx
_build_point = map_engine_consumer._build_point
_process_trace = map_engine_consumer._process_trace
TraceWindowAggregator = map_engine_consumer.TraceWindowAggregator

SAMPLE_GPX = os.path.join(os.path.dirname(__file__), "sample.gpx")


def test_gpx_parser_enriches_points():
    with open(SAMPLE_GPX, "rb") as f:
        content = f.read()
    points = list(parse_gpx(content))
    assert len(points) == 10
    assert points[0]["latitude"] == 3.8480
    assert points[0]["longitude"] == 11.5021
    assert points[1]["speed_kmh"] is not None
    assert points[1]["bearing"] is not None


def test_point_normalization():
    payload = {
        "trace_id": "integration-trace",
        "chauffeur_id": "driver-001",
        "latitude": 3.848,
        "longitude": 11.5021,
        "recorded_at": "2026-07-16T12:00:00Z",
    }
    point = _build_point(payload)
    assert point["trace_id"] == "integration-trace"
    assert point["chauffeur_id"] == "driver-001"


@patch.object(map_engine_consumer, "_map_match")
@patch.object(map_engine_consumer, "detect_new_edges")
@patch.object(map_engine_consumer, "store_matched_trace")
@patch.object(map_engine_consumer, "_create_producer")
def test_pipeline_processes_trace_window(
    mock_create_producer, mock_store_trace, mock_detect_edges, mock_map_match
):
    """Simulate a full window of points -> map match -> edge detection."""
    mock_map_match.return_value = {
        "matchings": [{"geometry": {"type": "LineString", "coordinates": [[11.5, 3.84], [11.51, 3.85]]}}]
    }
    mock_detect_edges.return_value = [
        {"edge_id": "edge-int-1", "geometry": {"type": "LineString", "coordinates": [[11.5, 3.84], [11.51, 3.85]]}, "status": "non_cartographie_osm", "confirmation_count": 1}
    ]
    mock_producer = MagicMock()
    mock_create_producer.return_value = mock_producer

    with open(SAMPLE_GPX, "rb") as f:
        content = f.read()
    points = list(parse_gpx(content))
    aggregator = TraceWindowAggregator(timeout_seconds=300, max_points=10)
    flushed = None
    for p in points:
        p["trace_id"] = "integration-trace"
        p["chauffeur_id"] = "driver-001"
        flushed = aggregator.add(p)

    assert flushed is not None
    assert len(flushed) == 10

    _process_trace("integration-trace", flushed)
    mock_map_match.assert_called_once()
    mock_detect_edges.assert_called_once()
    mock_store_trace.assert_called_once()
    mock_producer.produce.assert_called_once()
