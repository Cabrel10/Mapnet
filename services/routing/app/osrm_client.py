"""OSRM client for map matching and routing."""
import logging
import os
from typing import List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

OSRM_URL = os.environ.get("OSRM_URL", "http://router.project-osrm.org")
OSRM_LOCAL_URL = os.environ.get("OSRM_LOCAL_URL", "")


def _pick_base_url() -> str:
    """Prefer local OSRM if configured and reachable, else public fallback."""
    if OSRM_LOCAL_URL:
        try:
            r = httpx.get(f"{OSRM_LOCAL_URL}/nearest/v1/foot/0,0", timeout=2.0)
            if r.status_code < 500:
                return OSRM_LOCAL_URL
        except Exception:
            pass
    return OSRM_URL.rstrip("/")


def map_match(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Call OSRM match service for a polyline of points.

    points: list of dicts with latitude and longitude.
    Returns the matched geometry GeoJSON or raises an error.
    """
    if len(points) < 2:
        raise ValueError("Need at least two points for map matching")

    coords = ";".join(f"{p['longitude']},{p['latitude']}" for p in points)
    base = _pick_base_url()
    url = f"{base}/match/v1/foot/{coords}?overview=full&geometries=geojson&annotations=true"

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.error("OSRM request failed: %s", exc)
        raise

    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM match error: {data.get('message', data.get('code'))}")

    return data


def route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> Dict[str, Any]:
    """Calculate a route from origin to destination."""
    base = _pick_base_url()
    url = f"{base}/route/v1/foot/{from_lon},{from_lat};{to_lon},{to_lat}?overview=full&geometries=geojson"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM route error: {data.get('message', data.get('code'))}")
    return data


def nearest(lat: float, lon: float) -> Dict[str, Any]:
    """Find nearest OSM way to a point."""
    base = _pick_base_url()
    url = f"{base}/nearest/v1/foot/{lon},{lat}"
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url)
        r.raise_for_status()
    return r.json()
