"""Geofencing logic for CCAA drone compliance."""
import json
import logging
import os
from typing import List, Dict, Any

from shapely.geometry import shape, Polygon

logger = logging.getLogger(__name__)

_NOFLY_ZONES_CACHE: List[Dict[str, Any]] = []

NOFLY_FILE = os.environ.get(
    "NOFLY_ZONES_FILE",
    os.path.join(os.path.dirname(__file__), "..", "data", "nofly-zones.geojson"),
)


def load_nofly_zones_from_file() -> List[Dict[str, Any]]:
    """Load no-fly zones from GeoJSON."""
    if not os.path.exists(NOFLY_FILE):
        return []
    try:
        with open(NOFLY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Failed to load no-fly file: %s", exc)
        return []

    zones = []
    for feature in data.get("features", []):
        geom = feature.get("geometry")
        props = feature.get("properties", {})
        if not geom:
            continue
        try:
            shp = shape(geom)
        except Exception:
            continue
        zones.append({
            "zone_name": props.get("name", "Zone inconnue"),
            "zone_type": props.get("type", "restricted"),
            "altitude_max_m": props.get("altitude_max_m"),
            "geometry": shp,
        })
    return zones


def load_nofly_zones_from_db() -> List[Dict[str, Any]]:
    """Load no-fly zones from PostGIS if DATABASE_URL is available."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        database_url = os.environ.get(
            "DATABASE_URL", "postgresql://postgres:secure_password@postgis:5432/quamtechs_db"
        )
        engine = create_engine(database_url, future=True)
        SessionLocal = sessionmaker(bind=engine, future=True)
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT zone_name, zone_type, altitude_max_m,
                           ST_AsGeoJSON(geom) AS geom
                    FROM ccaa_nofly_zones
                    WHERE effective_until IS NULL OR effective_until > NOW()
                    """
                )
            ).mappings().all()
        zones = []
        for row in rows:
            geom_json = row.get("geom")
            if not geom_json:
                continue
            try:
                shp = shape(json.loads(geom_json))
            except Exception:
                continue
            zones.append({
                "zone_name": row["zone_name"],
                "zone_type": row["zone_type"],
                "altitude_max_m": row["altitude_max_m"],
                "geometry": shp,
            })
        return zones
    except Exception as exc:
        logger.warning("Failed to load DB no-fly zones: %s", exc)
        return []


def get_all_zones() -> List[Dict[str, Any]]:
    """Combine file and DB no-fly zones."""
    return load_nofly_zones_from_file() + load_nofly_zones_from_db()


def check_flight_plan(polygon: Polygon, altitude_m: int) -> Dict[str, Any]:
    """Check whether a flight plan intersects any no-fly zone."""
    zones = get_all_zones()
    conflicts = []
    for zone in zones:
        if zone["geometry"].intersects(polygon):
            alt_limit = zone.get("altitude_max_m")
            if alt_limit is None or altitude_m > alt_limit:
                conflicts.append({
                    "zone_name": zone["zone_name"],
                    "zone_type": zone["zone_type"],
                    "altitude_max_m": alt_limit,
                })

    if conflicts:
        return {
            "status": "rejected",
            "reason": "Flight plan intersects with no-fly zones",
            "conflicts": conflicts,
        }
    return {"status": "approved", "reason": "No conflict detected", "conflicts": []}
