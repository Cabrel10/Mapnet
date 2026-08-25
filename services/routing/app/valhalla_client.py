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
          costing: str = "auto", alternates: int = 0) -> Dict[str, Any]:
    """Itinéraire A->B avec narratives turn-by-turn.

    `alternates` : nombre d'itinéraires alternatifs demandés (0 = principal seul).
    """
    payload = {
        "locations": [
            {"lat": from_lat, "lon": from_lon},
            {"lat": to_lat, "lon": to_lon},
        ],
        "costing": costing,
        "directions_options": {"units": "kilometers", "language": "fr-FR"},
    }
    if alternates and alternates > 0:
        payload["alternates"] = int(alternates)
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{VALHALLA_URL}/route", json=payload)
        r.raise_for_status()
        return r.json()


def decode_polyline6(encoded: str) -> List[List[float]]:
    """Décode une polyline Valhalla (précision 6) -> liste [lon, lat] (ordre GeoJSON)."""
    coords: List[List[float]] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        for _unit in ("lat", "lon"):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if _unit == "lat":
                lat += delta
            else:
                lon += delta
        coords.append([lon / 1e6, lat / 1e6])
    return coords


def route_costed(from_lat: float, from_lon: float, to_lat: float, to_lon: float,
                 costing: str = "auto") -> Dict[str, Any]:
    """Itinéraire Valhalla avec VRAI profil (costing), renvoyé au format OSRM-like.

    Renvoie {distance(m), duration(s), geometry:{type:LineString, coordinates:[[lon,lat]...]}, steps}
    afin d'être interchangeable avec route_alternatives (OSRM) côté endpoint.
    Valhalla costings: auto, pedestrian, motorcycle, taxi, bicycle, bus, truck.
    """
    data = route(from_lat, from_lon, to_lat, to_lon, costing=costing)
    trip = data.get("trip", {})
    legs = trip.get("legs", [])
    if not legs:
        raise RuntimeError("valhalla: no legs")
    leg = legs[0]
    coords = decode_polyline6(leg.get("shape", ""))
    summ = trip.get("summary", {})
    # length est en km (units=kilometers) -> convertir en mètres ; time en secondes.
    dist_m = float(summ.get("length", 0.0)) * 1000.0
    dur_s = float(summ.get("time", 0.0))
    steps = []
    for m in leg.get("maneuvers", []):
        steps.append({
            "instruction": m.get("instruction"),
            "name": (m.get("street_names") or [None])[0],
            "distance": float(m.get("length", 0.0)) * 1000.0,
            "duration": float(m.get("time", 0.0)),
        })
    return {
        "distance": dist_m,
        "duration": dur_s,
        "geometry": {"type": "LineString", "coordinates": coords},
        "steps": steps,
        "costing": costing,
    }


def _trip_to_route(trip: Dict[str, Any]) -> Dict[str, Any]:
    legs = trip.get("legs", [])
    if not legs:
        return {}
    leg = legs[0]
    coords = decode_polyline6(leg.get("shape", ""))
    summ = trip.get("summary", {})
    steps = []
    for m in leg.get("maneuvers", []):
        steps.append({
            "instruction": m.get("instruction"),
            "name": (m.get("street_names") or [None])[0],
            "distance": float(m.get("length", 0.0)) * 1000.0,
            "duration": float(m.get("time", 0.0)),
        })
    return {
        "distance": float(summ.get("length", 0.0)) * 1000.0,
        "duration": float(summ.get("time", 0.0)),
        "geometry": {"type": "LineString", "coordinates": coords},
        "steps": steps,
    }


def route_alternatives_costed(from_lat: float, from_lon: float, to_lat: float,
                              to_lon: float, count: int = 3,
                              costing: str = "auto") -> Dict[str, Any]:
    """Alternatives Valhalla avec VRAI profil. Format {routes:[...]} OSRM-like."""
    n = max(1, min(int(count), 4))
    data = route(from_lat, from_lon, to_lat, to_lon,
                 costing=costing, alternates=n - 1)
    routes = []
    main = data.get("trip")
    if main:
        r0 = _trip_to_route(main)
        if r0:
            routes.append(r0)
    for alt in (data.get("alternates") or []):
        t = alt.get("trip") if isinstance(alt, dict) else None
        if t:
            r = _trip_to_route(t)
            if r:
                routes.append(r)
    return {"code": "Ok", "routes": routes, "engine": "valhalla", "costing": costing}


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
