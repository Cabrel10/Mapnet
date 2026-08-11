"""Routing Service - FastAPI entrypoint."""
import logging
import os
from typing import List

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from .osrm_client import map_match, route, nearest

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


@app.post("/api/v1/routing/route")
def calculate_route(req: RouteRequest):
    try:
        data = route(req.from_lat, req.from_lon, req.to_lat, req.to_lon)
    except Exception as exc:
        logger.error("Routing failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "routes": data.get("routes", [])}


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
