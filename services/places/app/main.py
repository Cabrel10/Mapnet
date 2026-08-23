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


def _resolve_database_url() -> str:
    """Pick a DATABASE_URL that actually works.

    The docker-compose default points at host ``postgis`` which only resolves
    inside the compose network. When the service is run directly on the host
    (uvicorn), ``postgis`` is unresolvable and every DB query returns HTTP 500.
    Fall back to 127.0.0.1 in that case.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    import socket

    host = "postgis"
    try:
        socket.gethostbyname(host)
    except OSError:
        host = "127.0.0.1"
        logger.warning("Host 'postgis' unresolvable; falling back to %s for DB", host)
    return f"postgresql://postgres:secure_password@{host}:5432/quamtechs_db"


DATABASE_URL = _resolve_database_url()
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
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


# --------------------------------------------------------------------------- #
# Unified Cameroon-first search                                                #
# --------------------------------------------------------------------------- #
# MAPNET is a Cameroon map. Search must (1) look across divisions (quartiers),  #
# named POI/establishments and named buildings, (2) rank exact / prefix / word #
# matches above loose substring matches, and (3) bias toward the user's        #
# current location and the target cities (Yaoundé, Douala, Bafoussam).          #
# Kept dependency-free (pure PostGIS + SQL scoring) so it works without         #
# Elasticsearch; ES can later index the same rows.                             #

# Approx city centres for proximity prior (lon, lat)
_CITY_CENTRES = {
    "yaounde": (11.5174, 3.8480),
    "douala": (9.7043, 4.0511),
    "bafoussam": (10.4176, 5.4783),
}


@app.get("/api/v1/places/search")
def search_places(
    q: str,
    limit: int = 20,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    kinds: Optional[str] = None,
):
    """Unified, ranked, Cameroon-first search.

    Parameters
    ----------
    q      : free-text query.
    limit  : max results.
    lat/lon: optional user position -> proximity boost.
    kinds  : optional CSV filter among {division, place, building}.
    """
    q = (q or "").strip()
    if not q:
        return {"status": "ok", "count": 0, "results": []}

    want = {k.strip() for k in (kinds or "division,place,building").split(",") if k.strip()}
    q_norm = q.lower()
    # Split into words so "Stade Olembe" matches "Stade d'Olembé" (apostrophe /
    # accent / punctuation insensitive). Every word must be present (AND).
    import re as _re

    words = [w for w in _re.split(r"[^0-9a-zA-Zàâäéèêëïîôöùûüç]+", q_norm) if w]
    if not words:
        words = [q_norm]
    like = f"%{q_norm}%"
    prefix = f"{q_norm}%"
    # user position, else Yaoundé centre as national default
    ulon, ulat = (lon, lat) if (lat is not None and lon is not None) else _CITY_CENTRES["yaounde"]

    # normalized column expression (accent + case folded)
    def _nx(col: str) -> str:
        return f"mapnet_norm({col})"

    # Text relevance score (0..100), computed the same way for every source.
    def _text_score(col: str) -> str:
        n = _nx(col)
        return f"""
            (CASE
                WHEN {n} = mapnet_norm(:q_norm)                 THEN 100
                WHEN {n} LIKE mapnet_norm(:prefix)              THEN 70
                WHEN {n} LIKE mapnet_norm(:like)                THEN 55
                ELSE 40
            END)"""

    # AND-of-words WHERE fragment: all query words present in the (normalized) name
    def _where_words(col: str) -> str:
        n = _nx(col)
        conds = " AND ".join(f"{n} LIKE mapnet_norm(:w{i})" for i in range(len(words)))
        return conds

    # proximity score: up to +25 within ~0 m, decaying to 0 by ~50 km
    prox = (
        "GREATEST(0, 25 - (ST_Distance(geom::geography, "
        "ST_SetSRID(ST_MakePoint(:ulon, :ulat),4326)::geography) / 2000.0))"
    )

    params = {
        "q_norm": q_norm, "like": like, "prefix": prefix,
        "ulon": ulon, "ulat": ulat, "limit": limit,
    }
    for i, w in enumerate(words):
        params[f"w{i}"] = f"%{w}%"

    selects = []
    if "division" in want:
        selects.append(f"""
            SELECT division_id AS id, name, subtype AS category, 'division' AS kind,
                   COALESCE(city,'') AS city,
                   ST_Y(ST_Centroid(geom)) AS latitude, ST_X(ST_Centroid(geom)) AS longitude,
                   ({_text_score('name')} + {prox} + 15) AS score
            FROM mapnet_divisions
            WHERE {_where_words('name')}
        """)
    if "place" in want:
        selects.append(f"""
            SELECT place_id AS id, name, category, 'place' AS kind,
                   COALESCE(city,'') AS city,
                   ST_Y(geom) AS latitude, ST_X(geom) AS longitude,
                   ({_text_score('name')} + {prox} + 10) AS score
            FROM raw_places
            WHERE {_where_words('name')}
        """)
    if "building" in want:
        selects.append(f"""
            SELECT building_id AS id, name, class AS category, 'building' AS kind,
                   COALESCE(city,'') AS city,
                   ST_Y(ST_Centroid(geom)) AS latitude, ST_X(ST_Centroid(geom)) AS longitude,
                   ({_text_score('name')} + {prox}) AS score
            FROM mapnet_buildings
            WHERE name IS NOT NULL AND name <> '' AND {_where_words('name')}
        """)

    if not selects:
        return {"status": "ok", "count": 0, "results": []}

    union_sql = "\nUNION ALL\n".join(f"({s})" for s in selects)
    final_sql = f"""
        SELECT * FROM (
            {union_sql}
        ) u
        WHERE score > 0
        ORDER BY score DESC, name ASC
        LIMIT :limit
    """

    try:
        with SessionLocal() as session:
            rows = session.execute(text(final_sql), params).mappings().all()
    except Exception as exc:  # surface a clean error instead of bare 500
        logger.exception("search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"search error: {exc}",
        ) from exc

    results = [
        {
            "id": r["id"], "name": r["name"], "category": r["category"],
            "kind": r["kind"], "city": r["city"],
            "latitude": r["latitude"], "longitude": r["longitude"],
            "score": round(float(r["score"]), 2),
        }
        for r in rows
    ]
    return {"status": "ok", "count": len(results), "query": q, "results": results}
