"""Places Service - FastAPI entrypoint."""
import logging
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .overpass_client import fetch_pois

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapNet Places Service", version="1.0.0")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "places")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:secure_password@postgis:5432/quamtechs_db"
)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)

SCRAPE_CITIES = [c.strip() for c in os.environ.get("SCRAPE_CITIES", "Yaoundé,Douala").split(",") if c.strip()]


class HealthResponse(BaseModel):
    status: str
    service: str


class POI(BaseModel):
    place_id: str
    name: str
    category: Optional[str] = None
    latitude: float
    longitude: float


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/api/v1/places/scrape")
def scrape_pois(city: str):
    try:
        pois = fetch_pois(city)
    except Exception as exc:
        logger.error("Scraping failed for %s: %s", city, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    inserted = 0
    with SessionLocal() as session:
        for p in pois:
            try:
                session.execute(
                    text(
                        """
                        INSERT INTO raw_places (place_id, name, category, source, geom, raw_response)
                        VALUES (:place_id, :name, :category, 'overpass',
                                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :raw)
                        ON CONFLICT (place_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            category = EXCLUDED.category,
                            raw_response = EXCLUDED.raw_response
                        """
                    ),
                    {
                        "place_id": p["place_id"],
                        "name": p["name"],
                        "category": p["category"],
                        "lat": p["latitude"],
                        "lon": p["longitude"],
                        "raw": p["raw_response"],
                    },
                )
                inserted += 1
            except Exception as exc:
                logger.error("Insert POI failed: %s", exc)
                continue
        session.commit()

    return {"status": "ok", "city": city, "pois_fetched": len(pois), "pois_inserted": inserted}


@app.post("/api/v1/places/scrape-all")
def scrape_all():
    results = []
    for city in SCRAPE_CITIES:
        try:
            res = scrape_pois(city)
            results.append(res)
        except HTTPException:
            results.append({"city": city, "status": "error"})
    return {"status": "ok", "results": results}


@app.get("/api/v1/places/nearby")
def nearby_places(lat: float, lon: float, radius: float = 500.0, category: Optional[str] = None):
    with SessionLocal() as session:
        sql = """
            SELECT place_id, name, category,
                   ST_Y(geom) AS latitude, ST_X(geom) AS longitude
            FROM raw_places
            WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)
        """
        params = {"lat": lat, "lon": lon, "radius": radius}
        if category:
            sql += " AND category = :category"
            params["category"] = category
        sql += " ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 100"
        rows = session.execute(text(sql), params).mappings().all()
    return {"status": "ok", "count": len(rows), "places": [dict(row) for row in rows]}


@app.get("/api/v1/places/search")
def search_places(q: str, limit: int = 20):
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT place_id, name, category,
                       ST_Y(geom) AS latitude, ST_X(geom) AS longitude
                FROM raw_places
                WHERE name ILIKE :q
                LIMIT :limit
                """
            ),
            {"q": f"%{q}%", "limit": limit},
        ).mappings().all()
    return {"status": "ok", "count": len(rows), "places": [dict(row) for row in rows]}
