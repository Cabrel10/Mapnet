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
    url = (
        f"{base}/route/v1/foot/{from_lon},{from_lat};{to_lon},{to_lat}"
        "?overview=full&geometries=geojson&steps=true&annotations=true"
    )
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


# OSM road classes considered "secondary" (vs primary/motorway/trunk).
_SECONDARY_CLASSES = {"secondary", "tertiary", "unclassified", "residential", "service", "track", "path", "living_street"}
# OSM surfaces that are NOT paved (chantier / non bitumé).
_UNPAVED_SURFACES = {"unpaved", "gravel", "dirt", "ground", "sand", "mud", "grass", "earth", "clay", "compacted"}


def route_alternatives(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float, count: int = 4
) -> Dict[str, Any]:
    """Return up to `count` alternative routes with surface/class annotations.

    Uses OSRM `alternatives=true` (capped by server at 3 routes max) and
    requests annotations so the caller can detect secondary / unpaved /
    construction segments. If the OSRM server returns fewer than `count`
    distinct routes, we synthesize extra candidates by nudging a waypoint
    slightly north/south/east/west of the straight midpoint (classic
    via-point diversification) and keep the best distinct ones.
    """
    base = _pick_base_url()
    coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
    url = (
        f"{base}/route/v1/driving/{coords}"
        "?overview=full&geometries=geojson&steps=true"
        "&annotations=duration,distance,speed"
        f"&alternatives={min(count - 1, 3)}"  # OSRM counts alternatives besides the main one
    )
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM route error: {data.get('message', data.get('code'))}")

    routes = data.get("routes", [])

    # If fewer than requested, generate via-point variants around the midpoint.
    if len(routes) < count:
        mid_lat = (from_lat + to_lat) / 2.0
        mid_lon = (from_lon + to_lon) / 2.0
        # ~1 km offsets in degrees
        offsets = [(0.01, 0.0), (-0.01, 0.0), (0.0, 0.01), (0.0, -0.01)]
        seen = {_route_signature(rt) for rt in routes}
        for dlat, dlon in offsets:
            if len(routes) >= count:
                break
            via = f"{from_lon},{from_lat};{mid_lon + dlon},{mid_lat + dlat};{to_lon},{to_lat}"
            vurl = f"{base}/route/v1/driving/{via}?overview=full&geometries=geojson&steps=true&annotations=duration,distance,speed"
            try:
                with httpx.Client(timeout=30.0) as client:
                    vr = client.get(vurl)
                    vr.raise_for_status()
                    vdata = vr.json()
            except httpx.HTTPError:
                continue
            if vdata.get("code") != "Ok":
                continue
            for vr_route in vdata.get("routes", []):
                sig = _route_signature(vr_route)
                if sig in seen:
                    continue
                seen.add(sig)
                vr_route["_via"] = [mid_lon + dlon, mid_lat + dlat]
                routes.append(vr_route)
                if len(routes) >= count:
                    break

    return {"code": "Ok", "routes": routes}


def _route_signature(route_obj: Dict[str, Any]) -> str:
    """Cheap signature to dedupe routes (rounded total distance+duration)."""
    d = round(route_obj.get("distance", 0) / 50)  # 50 m buckets
    t = round(route_obj.get("duration", 0) / 15)  # 15 s buckets
    return f"{d}:{t}"


def annotate_route_surfaces(route_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize secondary / unpaved / construction segments of a route.

    Returns counts + total distance per category so the UI can badge each
    itinerary ("2.3 km non bitumé", "1.1 km chantier", "route secondaire").
    """
    secondary_m = 0.0
    unpaved_m = 0.0
    construction_m = 0.0
    # Au Cameroun, les axes majeurs ont des refs P (provincial) et N (national)
    # en plus de A (autoroute). On les EXCLUT du classement "secondaire" :
    # P11/P1/N1 ne sont PAS des ruelles. Seule une classe highway explicite
    # (track/path/service/residential) OU une surface non bitumée doit baisser
    # la praticabilité ; à défaut de donnée on ne déclare PAS "secondaire".
    _MAJOR_REF_PREFIXES = ("A", "N", "P", "D", "R")
    total_m = 0.0
    known_surface_m = 0.0
    for leg in route_obj.get("legs", []):
        for step in leg.get("steps", []):
            dist = float(step.get("distance", 0.0) or 0.0)
            total_m += dist
            ref = str(step.get("ref", "") or "").strip().upper()
            name = str(step.get("name", "") or "").lower()
            surface = str(step.get("surface", "") or "").lower()
            highway = str(step.get("highway", "") or "").lower()
            if surface:
                known_surface_m += dist
            is_major = bool(ref) and ref.startswith(_MAJOR_REF_PREFIXES)
            # secondaire = petite voie UNIQUEMENT si pas un axe majeur
            if highway in _SECONDARY_CLASSES and not is_major:
                secondary_m += dist
            # non bitumé = surface explicitement non revêtue (jamais deviné)
            if surface in _UNPAVED_SURFACES or "unpaved" in name:
                unpaved_m += dist
            if "construction" in name or "chantier" in name or highway == "construction":
                construction_m += dist
    # Honnêteté des données : on ne déclare "praticable" que si on a une info
    # surface réelle ; sinon surface_inconnue (évite le faux "voie praticable").
    return {
        "secondary_m": round(secondary_m, 1),
        "unpaved_m": round(unpaved_m, 1),
        "construction_m": round(construction_m, 1),
        "has_unpaved": unpaved_m > 0,
        "has_construction": construction_m > 0,
        "total_m": round(total_m, 1),
        "surface_known": known_surface_m > 0,
    }
