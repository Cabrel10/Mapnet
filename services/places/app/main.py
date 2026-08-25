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

# Cameroon is UTC+1 (WAT), no DST.
import datetime as _dt

_WAT = _dt.timezone(_dt.timedelta(hours=1))
_DAY_IDX = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
_DAY_ORDER = ["mo", "tu", "we", "th", "fr", "sa", "su"]


def compute_open_status(opening_hours: Optional[str], now: Optional[_dt.datetime] = None):
    """Lightweight OSM `opening_hours` evaluator (dependency-free).

    Returns {"is_open": True|False|None, "label": str}. is_open is None
    ("unknown") when there are no hours or the rule is too complex to parse
    safely — we never guess. Supports the common Cameroon POI shapes:
      "24/7"
      "Mo-Fr 08:00-18:00"
      "Mo-Fr 08:00-12:00,14:00-18:00"
      "Mo-Sa 09:00-20:00; Su 10:00-14:00"
    """
    if not opening_hours or not opening_hours.strip():
        return {"is_open": None, "label": "unknown"}
    spec = opening_hours.strip().lower()
    if now is None:
        now = _dt.datetime.now(_WAT)
    if "24/7" in spec:
        return {"is_open": True, "label": "open (24/7)"}

    today = now.weekday()  # Mon=0
    cur_min = now.hour * 60 + now.minute

    def _day_matches(day_token: str) -> bool:
        day_token = day_token.strip()
        if not day_token:
            return True  # no day part => every day
        for part in day_token.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                a, b = a.strip()[:2], b.strip()[:2]
                if a in _DAY_IDX and b in _DAY_IDX:
                    ia, ib = _DAY_IDX[a], _DAY_IDX[b]
                    span = ([*range(ia, 7)] + [*range(0, ib + 1)]) if ia > ib else list(range(ia, ib + 1))
                    if today in span:
                        return True
            elif part[:2] in _DAY_IDX and _DAY_IDX[part[:2]] == today:
                return True
        return False

    def _time_open(time_token: str) -> Optional[bool]:
        matched_any = False
        for rng in time_token.split(","):
            rng = rng.strip()
            if "-" not in rng:
                continue
            s, e = rng.split("-", 1)
            try:
                sh, sm = (int(x) for x in s.strip().split(":"))
                eh, em = (int(x) for x in e.strip().split(":"))
            except ValueError:
                return None
            matched_any = True
            start = sh * 60 + sm
            end = eh * 60 + em
            if end <= start:  # crosses midnight
                if cur_min >= start or cur_min < end:
                    return True
            elif start <= cur_min < end:
                return True
        return False if matched_any else None

    import re as _re
    try:
        for rule in spec.split(";"):
            rule = rule.strip()
            if not rule:
                continue
            m = _re.match(r"^([a-z,\-\s]*?)\s*(\d{1,2}:\d{2}.*)$", rule)
            if not m:
                continue
            day_part, time_part = m.group(1), m.group(2)
            if not _day_matches(day_part):
                continue
            res = _time_open(time_part)
            if res is True:
                return {"is_open": True, "label": "open now"}
            if res is False:
                return {"is_open": False, "label": "closed now"}
    except Exception:  # never fail the request on a weird rule
        return {"is_open": None, "label": "unknown"}
    # A rule for today existed but none matched the current time => closed.
    return {"is_open": False, "label": "closed now"}


@app.get("/api/v1/places/search")
def search_places(
    q: str,
    limit: int = 20,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    kinds: Optional[str] = None,
    grouped: bool = False,
):
    """Unified, ranked, Cameroon-first search.

    Parameters
    ----------
    q       : free-text query.
    limit   : max results.
    lat/lon : optional user position -> proximity boost.
    kinds   : optional CSV filter among {division, place, building}.
    grouped : when true, also return a `groups` object splitting the results
              into districts / neighborhoods / places / buildings for the
              hierarchical search dropdown (the flat `results` list is kept
              for backward compatibility).
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
    payload = {"status": "ok", "count": len(results), "query": q, "results": results}
    if grouped:
        # Split ranked results into UI groups for the hierarchical dropdown.
        # A division is a "neighborhood" when its category says so, else a
        # "district". Flat `results` is kept for backward compatibility.
        groups = {
            "districts": [], "neighborhoods": [],
            "places": [], "buildings": [], "roads": [],
        }
        for r in results:
            if r["kind"] == "division":
                cat = (r.get("category") or "").lower()
                if cat in ("neighborhood", "quarter", "microhood"):
                    groups["neighborhoods"].append(r)
                else:
                    groups["districts"].append(r)
            elif r["kind"] == "building":
                groups["buildings"].append(r)
            else:
                groups["places"].append(r)
        payload["groups"] = groups
    return payload


@app.get("/api/v1/places/building-at")
def building_at(lat: float, lon: float, radius: float = 40.0):
    """Return named building(s) near a position.

    Backed by mapnet_building_labels (buildings labelled either by their own
    name or by the nearest POI within 25 m). Answers the "what building am I
    looking at / standing next to?" question for the map and navigation UI.
    """
    sql = """
        SELECT building_id, label, label_source, poi_category, class, city,
               latitude, longitude,
               ST_Distance(
                   ST_SetSRID(ST_MakePoint(longitude, latitude),4326)::geography,
                   ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography
               ) AS dist_m
        FROM mapnet_building_labels
        WHERE label IS NOT NULL
          AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(longitude, latitude),4326)::geography,
                  ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                  :radius)
        ORDER BY dist_m ASC
        LIMIT 10
    """
    try:
        with SessionLocal() as session:
            rows = session.execute(
                text(sql), {"lat": lat, "lon": lon, "radius": radius}
            ).mappings().all()
    except Exception as exc:
        logger.exception("building-at failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"building-at error: {exc}",
        ) from exc
    buildings = [
        {
            "building_id": r["building_id"], "label": r["label"],
            "label_source": r["label_source"], "poi_category": r["poi_category"],
            "class": r["class"], "city": r["city"],
            "latitude": r["latitude"], "longitude": r["longitude"],
            "distance_m": round(float(r["dist_m"]), 1),
        }
        for r in rows
    ]
    return {"status": "ok", "count": len(buildings), "buildings": buildings}


# ---------------------------------------------------------------------------
# nearest-district — reverse-geocode a click to its administrative division.
# Answers level-3 of the 3-level map pick (building / POI / district).
# ---------------------------------------------------------------------------
@app.get("/api/v1/places/nearest-district")
def nearest_district(lat: float, lon: float):
    # A point in Cameroon is contained by several *nested* divisions
    # (country > region > county > locality > neighborhood). Naive KNN
    # ordering (geom <-> point) returns the country polygon first because it
    # also contains the point (distance 0). We instead want the MOST SPECIFIC
    # division. Strategy:
    #   1. Prefer divisions that actually CONTAIN the point, smallest area
    #      first, and rank fine-grained subtypes (neighborhood/microhood)
    #      above coarse ones (locality/county/region/country).
    #   2. If nothing contains the point (offshore / sparse coverage), fall
    #      back to true nearest by geography distance.
    point = "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)"
    # subtype ranking: lower number = more specific (better)
    rank_expr = """
        CASE lower(COALESCE(subtype,''))
            WHEN 'microhood'    THEN 0
            WHEN 'neighborhood' THEN 1
            WHEN 'quarter'      THEN 1
            WHEN 'locality'     THEN 2
            WHEN 'county'       THEN 3
            WHEN 'region'       THEN 4
            WHEN 'country'      THEN 5
            ELSE 2
        END
    """
    contains_sql = f"""
        SELECT name, COALESCE(city,'') AS city, subtype, admin_level,
               ST_Distance(geom::geography, {point}::geography) AS dist_m,
               ST_Area(geom::geography) AS area_m2
        FROM mapnet_divisions
        WHERE geom IS NOT NULL
          AND ST_Contains(geom, {point})
        ORDER BY ({rank_expr}) ASC, area_m2 ASC
        LIMIT 1
    """
    nearest_sql = f"""
        SELECT name, COALESCE(city,'') AS city, subtype, admin_level,
               ST_Distance(geom::geography, {point}::geography) AS dist_m,
               ST_Area(geom::geography) AS area_m2
        FROM mapnet_divisions
        WHERE geom IS NOT NULL
          AND COALESCE(admin_level, 99) <> 0
        ORDER BY geom <-> {point}
        LIMIT 1
    """
    try:
        with SessionLocal() as session:
            r = session.execute(text(contains_sql), {"lat": lat, "lon": lon}).mappings().first()
            if not r:
                r = session.execute(text(nearest_sql), {"lat": lat, "lon": lon}).mappings().first()
    except Exception as exc:
        logger.exception("nearest-district failed")
        raise HTTPException(status_code=500, detail=f"nearest-district error: {exc}") from exc
    if not r:
        return {"status": "ok", "name": None, "city": None}
    return {
        "status": "ok",
        "name": r["name"],
        "city": r["city"],
        "subtype": r["subtype"],
        "admin_level": r["admin_level"],
        "distance_m": round(float(r["dist_m"]), 1),
        "area_m2": round(float(r["area_m2"]), 1),
    }


# ---------------------------------------------------------------------------
# categories — the distinct POI categories with counts (drives the UI filter).
# ---------------------------------------------------------------------------
_CATEGORY_ICONS = {
    "restaurant": "🍽️", "hotel": "🏨", "school": "🏫",
    "college_university": "🎓", "hospital": "🏥", "pharmacy": "💊",
    "bank": "🏦", "shopping": "🛍️", "beauty_salon": "💇",
    "spas": "🧖", "religious_organization": "⛪",
    "professional_services": "💼", "real_estate_service": "🏘️",
    "party_and_event_planning": "🎉", "gas_station": "⛽",
}


@app.get("/api/v1/places/categories")
def list_categories(min_count: int = 1):
    sql = """
        SELECT category, COUNT(*) AS n
        FROM raw_places
        WHERE category IS NOT NULL AND category <> ''
        GROUP BY category
        HAVING COUNT(*) >= :min_count
        ORDER BY n DESC
    """
    try:
        with SessionLocal() as session:
            rows = session.execute(text(sql), {"min_count": min_count}).mappings().all()
    except Exception as exc:
        logger.exception("categories failed")
        raise HTTPException(status_code=500, detail=f"categories error: {exc}") from exc
    cats = [
        {
            "category": r["category"],
            "count": int(r["n"]),
            "icon": _CATEGORY_ICONS.get((r["category"] or "").lower(), "📍"),
        }
        for r in rows
    ]
    return {"status": "ok", "count": len(cats), "categories": cats}


# ---------------------------------------------------------------------------
# layer-counts — real per-layer object counts straight from PostGIS.
#
# The PROD status bar previously showed a single misleading "Lieux 12 556"
# number (only raw_places). MapNet actually knows ~1.5M buildings, ~124k road
# segments, ~140 divisions, etc. This endpoint exposes the true universe so the
# UI can present honest per-layer counters. Read-only, cheap COUNT(*) queries.
# ---------------------------------------------------------------------------
# Cache mémoire TTL : on ne relance PAS 5 COUNT(*) (dont un sur 1,5M bâtiments)
# à chaque rafraîchissement d'interface. Pour les grosses tables on utilise
# l'estimation instantanée pg_class.reltuples (précise après ANALYZE) ; exact
# COUNT réservé aux petites tables. TTL par défaut 300 s (surchargable).
import time as _time  # noqa: E402

_LC_TTL = float(os.environ.get("LAYER_COUNTS_TTL", "300"))
_lc_cache: dict[str, object] = {"ts": 0.0, "data": None}

# (clé, table, exact?) — exact=True force COUNT(*) (petites tables) ;
# exact=False autorise l'estimation reltuples (grosses tables).
_LC_TARGETS = [
    ("pois", "raw_places", True),
    ("buildings", "mapnet_buildings", False),   # ~1.5M -> estimation
    ("named_buildings", "mapnet_building_labels", True),
    ("roads", "mapnet_edges", False),           # ~124k -> estimation
    ("districts", "mapnet_divisions", True),
]


def _compute_layer_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with SessionLocal() as session:
        for key, tbl, exact in _LC_TARGETS:
            try:
                if not exact:
                    # Estimation instantanée (pas de scan de table).
                    # NB: on filtre par relname (pas ::regclass) car psycopg2
                    # confond le param ":t" avec la syntaxe de cast "::".
                    est = session.execute(
                        text("SELECT reltuples::bigint FROM pg_class "
                             "WHERE relname = :t AND relkind = 'r'"),
                        {"t": tbl},
                    ).scalar()
                    n = int(est or 0)
                    # Si la table n'a jamais été ANALYZE (reltuples <= 0), COUNT réel.
                    if n <= 0:
                        n = int(session.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0)
                    counts[key] = n
                else:
                    counts[key] = int(
                        session.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0)
            except Exception:  # noqa: BLE001 — table manquante ne casse pas le reste
                counts[key] = 0
                session.rollback()  # sinon la transaction reste avortée
    return counts


@app.get("/api/v1/places/layer-counts")
def layer_counts(refresh: bool = False):
    now = _time.time()
    cached = _lc_cache.get("data")
    age = now - float(_lc_cache.get("ts") or 0.0)
    if cached is not None and not refresh and age < _LC_TTL:
        return {"status": "ok", "counts": cached, "cached": True,
                "age_s": round(age, 1), "ttl_s": _LC_TTL}
    try:
        counts = _compute_layer_counts()
    except Exception as exc:  # pragma: no cover
        logger.exception("layer-counts failed")
        if cached is not None:  # sert le cache périmé plutôt que 500
            return {"status": "stale", "counts": cached, "cached": True,
                    "error": str(exc)}
        raise HTTPException(status_code=500, detail=f"layer-counts error: {exc}") from exc
    _lc_cache["data"] = counts
    _lc_cache["ts"] = now
    return {"status": "ok", "counts": counts, "cached": False, "ttl_s": _LC_TTL}


# ---------------------------------------------------------------------------
# by-category — POIs of a category, optionally near a point, with open status.
# ---------------------------------------------------------------------------
@app.get("/api/v1/places/by-category")
def by_category(
    category: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: Optional[float] = None,
    open_now: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    category = (category or "").strip()
    if not category:
        raise HTTPException(status_code=400, detail="category is required")

    params = {"category": category.lower(), "limit": limit, "offset": offset}
    where = ["lower(category) = :category"]
    dist_expr = "NULL"
    order = "name ASC"
    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon})
        dist_expr = (
            "ST_Distance(geom::geography, "
            "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography)"
        )
        order = "dist_m ASC NULLS LAST"
        if radius:
            params["radius"] = radius
            where.append(
                "ST_DWithin(geom::geography, "
                "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :radius)"
            )
    sql = f"""
        SELECT place_id, name, category, subcategory, address, phone, website,
               rating, opening_hours, description,
               ST_Y(geom) AS latitude, ST_X(geom) AS longitude,
               {dist_expr} AS dist_m
        FROM raw_places
        WHERE {' AND '.join(where)}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """
    try:
        with SessionLocal() as session:
            rows = session.execute(text(sql), params).mappings().all()
    except Exception as exc:
        logger.exception("by-category failed")
        raise HTTPException(status_code=500, detail=f"by-category error: {exc}") from exc

    results = []
    for r in rows:
        st = compute_open_status(r["opening_hours"])
        if open_now and st["is_open"] is not True:
            continue
        results.append({
            "place_id": r["place_id"], "name": r["name"],
            "category": r["category"], "subcategory": r["subcategory"],
            "address": r["address"], "phone": r["phone"], "website": r["website"],
            "rating": float(r["rating"]) if r["rating"] is not None else None,
            "opening_hours": r["opening_hours"], "description": r["description"],
            "latitude": r["latitude"], "longitude": r["longitude"],
            "distance_m": round(float(r["dist_m"]), 1) if r["dist_m"] is not None else None,
            "is_open": st["is_open"], "open_status": st["label"],
        })
    return {"status": "ok", "count": len(results), "category": category, "results": results}


# ---------------------------------------------------------------------------
# status — is a place open now? by place_id or nearest to lat/lon.
# ---------------------------------------------------------------------------
@app.get("/api/v1/places/status")
def place_status(
    id: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
):
    if id:
        sql = "SELECT place_id, name, opening_hours FROM raw_places WHERE place_id = :id LIMIT 1"
        params = {"id": id}
    elif lat is not None and lon is not None:
        sql = (
            "SELECT place_id, name, opening_hours FROM raw_places "
            "WHERE geom IS NOT NULL "
            "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon,:lat),4326) LIMIT 1"
        )
        params = {"lat": lat, "lon": lon}
    else:
        raise HTTPException(status_code=400, detail="provide id or lat+lon")
    try:
        with SessionLocal() as session:
            r = session.execute(text(sql), params).mappings().first()
    except Exception as exc:
        logger.exception("status failed")
        raise HTTPException(status_code=500, detail=f"status error: {exc}") from exc
    if not r:
        raise HTTPException(status_code=404, detail="place not found")
    st = compute_open_status(r["opening_hours"])
    return {
        "status": "ok", "place_id": r["place_id"], "name": r["name"],
        "opening_hours": r["opening_hours"],
        "is_open": st["is_open"], "open_status": st["label"],
    }
