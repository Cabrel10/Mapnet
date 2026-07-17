"""Overpass client for open POI extraction."""
import logging
import os
from typing import List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

OSM_API_URL = os.environ.get("OSM_API_URL", "https://overpass-api.de/api/interpreter")


def build_query(city: str) -> str:
    return f"""
[out:json];
area["name"="{city}"]->.searchArea;
(
  node["amenity"~"restaurant|pharmacy|fuel|hospital|school|clinic|bank"](area.searchArea);
  node["shop"~"supermarket|kiosk|convenience|general"](area.searchArea);
);
out body;
"""


def fetch_pois(city: str) -> List[Dict[str, Any]]:
    """Fetch POIs from Overpass API for a given city."""
    query = build_query(city)
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(OSM_API_URL, data={"data": query})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.error("Overpass request failed for %s: %s", city, exc)
        raise

    elements = data.get("elements", [])
    pois = []
    for el in elements:
        if el.get("type") != "node":
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "Point d'intérêt local")
        category = tags.get("amenity") or tags.get("shop") or "unknown"
        pois.append({
            "place_id": str(el.get("id")),
            "name": name,
            "category": category,
            "subcategory": tags.get(category),
            "latitude": el.get("lat"),
            "longitude": el.get("lon"),
            "raw_response": tags,
        })
    return pois
