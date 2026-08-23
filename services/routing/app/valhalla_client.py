"""Valhalla local client — routing, map matching (trace_attributes / trace_route).

MAPNET parle à Valhalla local (jamais le serveur public). Le client mobile ne
parle jamais directement à Valhalla : il passe par l'API routing MAPNET.

Endpoints Valhalla utilisés (cf. https://valhalla.github.io/valhalla/api/) :
  GET  /status
  POST /route
  POST /trace_route        (map matching -> itinéraire reconstruit)
  POST /trace_attributes   (map matching -> attributs par segment)
"""
import os
from typing import Any, Dict, List

import httpx

VALHALLA_URL = os.environ.get("VALHALLA_URL", "http://127.0.0.1:8002").rstrip("/")
_TIMEOUT = float(os.environ.get("VALHALLA_TIMEOUT", "30"))


def available() -> bool:
    """True si Valhalla local répond à /status."""
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{VALHALLA_URL}/status")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def status() -> Dict[str, Any]:
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(f"{VALHALLA_URL}/status")
        r.raise_for_status()
        return r.json()


def route(from_lat: float, from_lon: float, to_lat: float, to_lon: float,
          costing: str = "auto") -> Dict[str, Any]:
    """Itinéraire A->B avec narratives turn-by-turn."""
    payload = {
        "locations": [
            {"lat": from_lat, "lon": from_lon},
            {"lat": to_lat, "lon": to_lon},
        ],
        "costing": costing,
        "directions_options": {"units": "kilometers", "language": "fr-FR"},
    }
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{VALHALLA_URL}/route", json=payload)
        r.raise_for_status()
        return r.json()


def _shape(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    shape = []
    for p in points:
        pt = {"lat": p.get("latitude", p.get("lat")),
              "lon": p.get("longitude", p.get("lon"))}
        if p.get("time") is not None:
            pt["time"] = p["time"]
        if p.get("accuracy") is not None:
            pt["accuracy"] = p["accuracy"]
        shape.append(pt)
    return shape


def trace_attributes(points: List[Dict[str, Any]], costing: str = "auto"
                     ) -> Dict[str, Any]:
    """Map matching -> attributs par segment (edges, vitesse, noms de rue).

    Idéal pour transformer une trace GPS bruitée en segments routiers réels.
    """
    payload = {
        "shape": _shape(points),
        "costing": costing,
        "shape_match": "map_snap",
        "directions_options": {"units": "kilometers", "language": "fr-FR"},
    }
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{VALHALLA_URL}/trace_attributes", json=payload)
        r.raise_for_status()
        return r.json()


def trace_route(points: List[Dict[str, Any]], costing: str = "auto"
                ) -> Dict[str, Any]:
    """Map matching -> itinéraire reconstruit avec manoeuvres."""
    payload = {
        "shape": _shape(points),
        "costing": costing,
        "shape_match": "map_snap",
        "directions_options": {"units": "kilometers", "language": "fr-FR"},
    }
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{VALHALLA_URL}/trace_route", json=payload)
        r.raise_for_status()
        return r.json()
