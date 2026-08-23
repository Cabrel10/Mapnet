"""Routing Service - FastAPI entrypoint."""
import logging
import math
import os
from typing import List

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from .osrm_client import map_match, route, nearest, route_alternatives, annotate_route_surfaces
from . import valhalla_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapNet Routing Service", version="1.0.0")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "routing")


class Point(BaseModel):
    latitude: float
    longitude: float


class MapMatchRequest(BaseModel):
    points: List[Point]


class RouteRequest(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/api/v1/routing/map-match")
def map_match_route(req: MapMatchRequest):
    if len(req.points) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need at least 2 points")
    try:
        data = map_match([p.model_dump() for p in req.points])
    except Exception as exc:
        logger.error("Map matching failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "matchings": data.get("matchings", []), "tracepoints": data.get("tracepoints", [])}


def _valhalla_to_osrm_route(data: dict) -> dict:
    """Adapt a Valhalla /route response to the OSRM-style {routes:[...]} shape
    the mobile client already consumes, so switching engines is transparent."""
    trip = data.get("trip", {})
    legs = trip.get("legs", [])
    summary = trip.get("summary", {})
    steps = []
    if legs:
        for m in legs[0].get("maneuvers", []):
            steps.append({
                "instruction": m.get("instruction"),
                "distance": (m.get("length") or 0) * 1000.0,  # km -> m
                "duration": m.get("time"),
                "name": (m.get("street_names") or [None])[0],
            })
    return {
        "routes": [{
            "distance": (summary.get("length") or 0) * 1000.0,  # km -> m
            "duration": summary.get("time"),
            "geometry": legs[0].get("shape") if legs else None,
            "legs": [{"steps": steps}],
            "engine": "valhalla",
        }]
    }


@app.post("/api/v1/routing/route")
def calculate_route(req: RouteRequest, engine: str = "auto"):
    """Compute a route.

    engine=auto (default): Valhalla local first, OSRM fallback on failure.
    engine=valhalla | osrm: force a specific engine.

    Valhalla is preferred because its road graph is derived from the same
    OSM/Overture-aligned data MAPNET displays, reducing 'route to a non-existent
    road' artifacts seen with the legacy OSRM public backend.
    """
    engine = (engine or "auto").lower()
    used = None
    # Try Valhalla unless OSRM explicitly forced
    if engine in ("auto", "valhalla"):
        try:
            vdata = valhalla_client.route(req.from_lat, req.from_lon,
                                          req.to_lat, req.to_lon)
            out = _valhalla_to_osrm_route(vdata)
            out["status"] = "ok"
            out["engine"] = "valhalla"
            return out
        except Exception as exc:
            logger.warning("Valhalla route failed (%s); engine=%s", exc, engine)
            if engine == "valhalla":
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                    detail=f"valhalla: {exc}") from exc
            used = "osrm-fallback"
    # OSRM path (explicit or fallback)
    try:
        data = route(req.from_lat, req.from_lon, req.to_lat, req.to_lon)
    except Exception as exc:
        logger.error("Routing failed (osrm): %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "engine": used or "osrm", "routes": data.get("routes", [])}


@app.get("/api/v1/routing/nearest")
def nearest_point(lat: float, lon: float):
    try:
        data = nearest(lat, lon)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "result": data}


# ---------------------------------------------------------------------------
# Guided navigation endpoint: position -> destination.
#
# Returns a compact, navigation-ready payload consumed by BOTH the web
# console and the mobile collection app:
#   - distance (m) / duration (s) totals
#   - geometry as GeoJSON LineString (directly drawable on MapLibre)
#   - steps: ordered maneuvers with type/modifier/location/distance so the
#     client can do turn-by-turn tracking ("dans 50m tournez a gauche")
# ---------------------------------------------------------------------------

_MANEUVER_LABELS_FR = {
    "turn": "Tournez",
    "new name": "Continuez",
    "depart": "Démarrez",
    "arrive": "Vous êtes arrivé",
    "merge": "Rejoignez la voie",
    "on ramp": "Prenez la bretelle",
    "off ramp": "Quittez par la bretelle",
    "fork": "Prenez la fourche",
    "end of road": "En fin de route",
    "continue": "Continuez",
    "roundabout": "Au rond-point",
    "rotary": "Au rond-point",
    "roundabout turn": "Au rond-point",
    "notification": "Attention",
    "exit roundabout": "Sortez du rond-point",
    "exit rotary": "Sortez du rond-point",
}

_MODIFIER_LABELS_FR = {
    "left": "à gauche",
    "right": "à droite",
    "sharp left": "fortement à gauche",
    "sharp right": "fortement à droite",
    "slight left": "légèrement à gauche",
    "slight right": "légèrement à droite",
    "straight": "tout droit",
    "uturn": "en demi-tour",
}


def _instruction_fr(maneuver: dict, road_name: str) -> str:
    """Build a human-readable French instruction from an OSRM maneuver."""
    mtype = str(maneuver.get("type", "continue")).lower()
    modifier = str(maneuver.get("modifier", "") or "").lower()
    base = _MANEUVER_LABELS_FR.get(mtype, "Continuez")
    if mtype == "arrive":
        return base
    mod = _MODIFIER_LABELS_FR.get(modifier, "")
    parts = [base]
    if mod:
        parts.append(mod)
    if road_name:
        parts.append(f"sur {road_name}")
    return " ".join(parts)


@app.post("/api/v1/routing/navigate")
def navigate(req: RouteRequest):
    """Guided navigation from current position to destination.

    Response shape (stable contract for web + mobile):
    {
      "status": "ok",
      "route": {
        "distance": float,          # meters
        "duration": float,          # seconds
        "geometry": GeoJSON LineString,
        "steps": [
          {"instruction": str, "maneuver": str, "modifier": str,
           "location": [lon, lat], "distance": float, "duration": float}
        ]
      }
    }
    """
    try:
        data = route(req.from_lat, req.from_lon, req.to_lat, req.to_lon)
    except Exception as exc:
        logger.error("Navigate routing failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    routes = data.get("routes", [])
    if not routes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun itinéraire trouvé")

    r0 = routes[0]
    steps = []
    for leg in r0.get("legs", []):
        for s in leg.get("steps", []):
            maneuver = s.get("maneuver", {}) or {}
            road_name = s.get("name", "") or ""
            steps.append({
                "instruction": _instruction_fr(maneuver, road_name),
                "maneuver": maneuver.get("type", ""),
                "modifier": maneuver.get("modifier", ""),
                "location": maneuver.get("location", []),  # [lon, lat]
                "distance": s.get("distance", 0.0),
                "duration": s.get("duration", 0.0),
                "name": road_name,
            })

    return {
        "status": "ok",
        "route": {
            "distance": r0.get("distance", 0.0),
            "duration": r0.get("duration", 0.0),
            "geometry": r0.get("geometry", {}),
            "steps": steps,
        },
    }




# ---------------------------------------------------------------------------
# Helpers: cardinality (N/S/E/O) + named steps (ronds-points / carrefours)
# ---------------------------------------------------------------------------
_CARD_FR = [
    ("N", 337.5, 360.0), ("N", 0.0, 22.5),
    ("NE", 22.5, 67.5), ("E", 67.5, 112.5), ("SE", 112.5, 157.5),
    ("S", 157.5, 202.5), ("SO", 202.5, 247.5), ("O", 247.5, 292.5),
    ("NO", 292.5, 337.5),
]


def _bearing_cardinal(lat1, lon1, lat2, lon2):
    """Bearing initial (deg) entre deux points -> cardinal francais (N/NE/E...)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    for name, lo, hi in _CARD_FR:
        if lo <= brg < hi:
            return name
    return "N"


def _route_cardinality(geometry):
    """Cardinalite globale depart->arrivee d'une geometrie GeoJSON LineString."""
    coords = (geometry or {}).get("coordinates") or []
    if len(coords) < 2:
        return {"bearing": "?", "from_to": ""}
    a, b = coords[0], coords[-1]  # [lon, lat]
    card = _bearing_cardinal(a[1], a[0], b[1], b[0])
    return {"bearing": card, "from_to": f"depart -> {card} -> arrivee"}


def _named_steps(route_obj, max_steps=12):
    """Extrait les etapes avec un nom de voie / rond-point / carrefour.

    Garde surtout les maneuvers 'roundabout' / 'rotary' (ronds-points) et les
    changements de voie nommes, pour guider l'utilisateur avec des reperes
    concrets au lieu d'une simple distance/duree.
    """
    out = []
    for leg in route_obj.get("legs", []):
        for s in leg.get("steps", []):
            man = s.get("maneuver", {}) or {}
            mtype = str(man.get("type", "")).lower()
            name = str(s.get("name", "") or "")
            ref = str(s.get("ref", "") or "")
            label = name or ref
            is_roundabout = mtype in ("roundabout", "rotary")
            # garder ronds-points, arrives/departs, et voies nommees
            keep = is_roundabout or mtype in ("depart", "arrive") or bool(label)
            if not keep:
                continue
            instruction = _instruction_fr(man, label)
            if is_roundabout:
                exit_n = man.get("exit", "")
                instruction = f"Rond-point {label or ''} (sortie {exit_n})".strip()
            out.append({
                "instruction": instruction,
                "name": label,
                "maneuver": mtype,
                "modifier": str(man.get("modifier", "") or ""),
                "distance": float(s.get("distance", 0.0) or 0.0),
                "location": man.get("location", []),
            })
            if len(out) >= max_steps:
                return out
    return out


# ---------------------------------------------------------------------------
# Multi-itinerary endpoint: up to 4 routes per destination.
#
# Each itinerary is annotated with secondary / unpaved (non bitumé) /
# construction segment distances so the client can badge them and let the
# user pick (fastest paved vs scenic secondary vs avoiding chantiers).
# ---------------------------------------------------------------------------


@app.post("/api/v1/routing/alternatives")
def alternatives(req: RouteRequest, count: int = 4):
    """Return up to `count` (default 4) itineraries with surface badges.

    Response shape:
    {
      "status": "ok",
      "count": int,
      "routes": [
        {
          "rank": int,
          "distance": float, "duration": float,
          "geometry": GeoJSON LineString,
          "badges": {
            "secondary_m": float, "unpaved_m": float, "construction_m": float,
            "has_unpaved": bool, "has_construction": bool
          }
        }, ...
      ]
    }
    """
    n = max(1, min(int(count), 4))
    try:
        data = route_alternatives(
            req.from_lat, req.from_lon, req.to_lat, req.to_lon, count=n
        )
    except Exception as exc:
        logger.error("Alternatives routing failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    routes = data.get("routes", [])
    if not routes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun itinéraire trouvé")

    # Sort by duration ascending so rank 1 = fastest.
    routes = sorted(routes, key=lambda r: r.get("duration", 0.0))[:n]
    out = []
    for i, r in enumerate(routes, start=1):
        geom = r.get("geometry", {})
        out.append({
            "rank": i,
            "distance": r.get("distance", 0.0),
            "duration": r.get("duration", 0.0),
            "geometry": geom,
            "badges": annotate_route_surfaces(r),
            "cardinal": _route_cardinality(geom),
            "steps": _named_steps(r),
        })

    return {"status": "ok", "count": len(out), "routes": out}


# ---------------------------------------------------------------------------
# Valhalla local (moteur principal) — fallback OSRM conservé sur les endpoints
# historiques ci-dessus. MAPNET parle à Valhalla ; le client mobile parle à MAPNET.
# ---------------------------------------------------------------------------

@app.get("/api/v1/routing/engines")
def engines():
    """Diagnostic : quels moteurs de routage sont disponibles."""
    va = valhalla_client.available()
    return {
        "valhalla": {"available": va, "url": valhalla_client.VALHALLA_URL},
        "osrm": {"available": True, "note": "fallback historique"},
        "primary": "valhalla" if va else "osrm",
    }


@app.get("/api/v1/routing/valhalla/status")
def valhalla_status():
    try:
        return valhalla_client.status()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"valhalla indisponible: {exc}") from exc


@app.post("/api/v1/routing/route-v")
def route_valhalla(req: RouteRequest, costing: str = "auto"):
    """Itinéraire via Valhalla local avec narratives FR turn-by-turn."""
    try:
        data = valhalla_client.route(req.from_lat, req.from_lon,
                                     req.to_lat, req.to_lon, costing=costing)
    except Exception as exc:
        logger.error("Valhalla route failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=str(exc)) from exc
    trip = data.get("trip", {})
    legs = trip.get("legs", [])
    maneuvers = []
    if legs:
        for m in legs[0].get("maneuvers", []):
            maneuvers.append({
                "instruction": m.get("instruction"),
                "distance_km": m.get("length"),
                "time_s": m.get("time"),
                "street": (m.get("street_names") or [None])[0],
            })
    return {
        "status": "ok",
        "engine": "valhalla",
        "summary": trip.get("summary", {}),
        "maneuvers": maneuvers,
        "shape": legs[0].get("shape") if legs else None,
    }


@app.post("/api/v1/routing/trace-attributes")
def trace_attributes_ep(req: MapMatchRequest, costing: str = "auto"):
    """Map matching Valhalla : trace GPS bruitée -> segments routiers + vitesses."""
    if len(req.points) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Need at least 2 points")
    try:
        data = valhalla_client.trace_attributes(
            [p.model_dump() for p in req.points], costing=costing)
    except Exception as exc:
        logger.error("Valhalla trace_attributes failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=str(exc)) from exc
    edges = []
    for e in data.get("edges", []):
        edges.append({
            "names": e.get("names", []),
            "length_km": e.get("length"),
            "speed": e.get("speed"),
            "road_class": e.get("road_class"),
            "way_id": e.get("way_id"),
        })
    return {
        "status": "ok",
        "engine": "valhalla",
        "edges": edges,
        "matched_points": data.get("matched_points", []),
    }
