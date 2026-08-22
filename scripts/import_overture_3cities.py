#!/usr/bin/env python3
"""
import_overture_3cities.py — import Overture Maps pour Douala/Yaoundé/Bafoussam.

Usage :
  python3 import_overture_3cities.py --phase places
  python3 import_overture_3cities.py --phase segments
  python3 import_overture_3cities.py --phase divisions
  python3 import_overture_3cities.py --phase buildings  # lourd, en dernier
  python3 import_overture_3cities.py --phase all        # enchaîne tout
  python3 import_overture_3cities.py --phase buildings --city bafoussam

Idempotent : ON CONFLICT DO NOTHING partout. Enrichissement additif —
aucune donnée existante (OSM ou Overture) n'est jamais supprimée/écrasée.
"""

import argparse
import json
import os
import subprocess
import sys
import psycopg2
from pathlib import Path

OV = "/tmp/overture_venv/bin/overturemaps"
WORKDIR = Path("/tmp/overture_3cities")
WORKDIR.mkdir(exist_ok=True)
DBNAME = "quamtechs_db"
DBUSER = os.environ.get("PGUSER", "postgres")
DBPASS = os.environ.get("PGPASSWORD", "secure_password")
DBHOST = os.environ.get("PGHOST", "127.0.0.1")
DBPORT = int(os.environ.get("PGPORT", "5432"))


def connect():
    return psycopg2.connect(dbname=DBNAME, user=DBUSER, password=DBPASS,
                            host=DBHOST, port=DBPORT)

CITIES = {
    "yaounde":   {"bbox": "11.35,3.70,11.65,4.10", "label": "Yaoundé"},
    "douala":    {"bbox": "9.55,3.80,10.00,4.35",  "label": "Douala"},
    "bafoussam": {"bbox": "10.30,5.35,10.55,5.65", "label": "Bafoussam"},
}


def run(cmd, timeout=600):
    print(f"$ {cmd[:120]}...")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT après {timeout}s")
        return 124
    if r.returncode != 0 and r.stderr:
        print(r.stderr[-400:])
    return r.returncode


def download(city, theme, overture_type):
    """Télécharge si le fichier n'existe pas encore (skip idempotent)."""
    out = WORKDIR / f"{city}_{theme}.geojson"
    if out.exists() and out.stat().st_size > 1000:
        print(f"  skip (déjà téléchargé) : {out} ({out.stat().st_size//1024} KB)")
        return out
    bbox = CITIES[city]["bbox"]
    print(f"  downloading {city}/{theme} (bbox={bbox})...")
    run(f"{OV} download --bbox={bbox} -f geojson --type={overture_type} -o {out}",
        timeout=3600)
    count = 0
    if out.exists():
        try:
            count = len(json.load(open(out))["features"])
        except Exception:
            count = -1
    print(f"  -> {count} features : {out}")
    return out


def pg(sql, fetch=False):
    con = connect()
    cur = con.cursor()
    cur.execute(sql)
    result = cur.fetchall() if fetch else None
    con.commit()
    con.close()
    return result


def _trunc(v, n):
    if v is None:
        return None
    v = str(v)
    return v[:n] if len(v) > n else v


def import_places(city):
    f = download(city, "places", "place")
    data = json.load(open(f))
    inserted = 0
    warns = 0
    con = connect()
    cur = con.cursor()
    idx = 0
    for feat in data["features"]:
        p = feat.get("properties") or {}
        g = feat.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"]
        pid = _trunc(p.get("id") or f"ovt-{city}-{idx}", 100)
        idx += 1
        names = p.get("names") or {}
        name = _trunc(names.get("primary") if isinstance(names, dict) else None, 250)
        cats = p.get("categories") or {}
        cat = _trunc(cats.get("primary") if isinstance(cats, dict) else None, 50)
        addrs = p.get("addresses") or []
        addr = addrs[0].get("freeform") if addrs and isinstance(addrs[0], dict) else None
        raw = json.dumps({k: p.get(k) for k in
                          ("categories", "addresses", "confidence", "brand")
                          if k in p})
        # savepoint per row so a bad row never discards the batch
        cur.execute("SAVEPOINT sp;")
        try:
            cur.execute(
                """INSERT INTO raw_places
                   (place_id,name,category,address,source,geom,
                    raw_response,validated,city)
                   VALUES (%s,%s,%s,%s,'overture',
                           ST_SetSRID(ST_MakePoint(%s,%s),4326),
                           %s::jsonb,FALSE,%s)
                   ON CONFLICT (place_id) DO NOTHING;""",
                (pid, name, cat, addr, lon, lat, raw, city))
            inserted += cur.rowcount
            cur.execute("RELEASE SAVEPOINT sp;")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp;")
            warns += 1
            if warns <= 3:
                print(f"  warn: {e}")
    con.commit()
    con.close()
    total = pg(f"SELECT count(*) FROM raw_places WHERE city='{city}'", fetch=True)[0][0]
    print(f"  {city}/places: +{inserted} inserts, {warns} warns, {total} total (city)")


def import_segments(city):
    f = download(city, "segments", "segment")
    stg = f"_stg_seg_{city}"
    run(f"sudo -u postgres ogr2ogr -f PostgreSQL 'PG:dbname={DBNAME}' {f} "
        f"-nln {stg} -overwrite -where \"subtype='road'\" "
        f"-lco GEOMETRY_NAME=geom -t_srs EPSG:4326 -nlt LINESTRING",
        timeout=900)
    pg(f"""INSERT INTO mapnet_edges
        (edge_id,name,highway_type,surface,oneway,length_m,geom,
         status,data_source,confirmation_count,first_seen_at,last_seen_at,city)
        SELECT left('ovt-{city}-'||id,100),
          (names::json->>'primary'),
          class,
          (road_surface->0->>'value'),
          FALSE,
          ST_Length(geom::geography),
          ST_SetSRID(geom,4326),
          'osm_existing','overture',1,now(),now(),'{city}'
        FROM {stg}
        WHERE id IS NOT NULL
        ON CONFLICT (edge_id) DO NOTHING;""")
    pg(f"DROP TABLE IF EXISTS {stg};")
    count = pg(f"SELECT count(*) FROM mapnet_edges WHERE city='{city}' "
               f"AND data_source='overture'", fetch=True)[0][0]
    print(f"  {city}/segments: {count} total overture edges (city)")


def import_divisions(city):
    f = download(city, "divisions", "division_area")
    stg = f"_stg_div_{city}"
    run(f"sudo -u postgres ogr2ogr -f PostgreSQL 'PG:dbname={DBNAME}' {f} "
        f"-nln {stg} -overwrite -where \"country='CM'\" "
        f"-lco GEOMETRY_NAME=geom -t_srs EPSG:4326 -nlt PROMOTE_TO_MULTI",
        timeout=600)
    pg(f"""INSERT INTO mapnet_divisions
        (division_id,name,subtype,admin_level,country,source,geom,city)
        SELECT division_id,(names::json->>'primary'),subtype,admin_level,
               country,'overture',ST_Multi(geom),'{city}'
        FROM {stg}
        WHERE division_id IS NOT NULL
        ON CONFLICT (division_id) DO NOTHING;""")
    pg(f"DROP TABLE IF EXISTS {stg};")
    count = pg(f"SELECT count(*) FROM mapnet_divisions WHERE city='{city}'",
               fetch=True)[0][0]
    print(f"  {city}/divisions: {count} total (city)")


def import_buildings(city):
    """Le plus lourd. Import via ogr2ogr staging -> mapnet_buildings."""
    f = download(city, "buildings", "building")
    stg = f"_stg_bld_{city}"
    run(f"sudo -u postgres ogr2ogr -f PostgreSQL 'PG:dbname={DBNAME}' {f} "
        f"-nln {stg} -overwrite "
        f"-lco GEOMETRY_NAME=geom -t_srs EPSG:4326 "
        f"-nlt MULTIPOLYGON -lco SPATIAL_INDEX=GIST",
        timeout=3600)
    # height peut être absent/typé float par ogr2ogr ; cast prudent
    pg(f"""INSERT INTO mapnet_buildings
        (building_id,name,class,height_m,num_floors,source,geom,city)
        SELECT left(id,100),
          (names::json->>'primary'),
          subtype,
          CASE WHEN height IS NOT NULL THEN height::numeric ELSE NULL END,
          num_floors,
          'overture',
          ST_Multi(geom),
          '{city}'
        FROM {stg}
        WHERE id IS NOT NULL
        ON CONFLICT (building_id) DO NOTHING;""")
    pg(f"DROP TABLE IF EXISTS {stg};")
    count = pg(f"SELECT count(*) FROM mapnet_buildings WHERE city='{city}'",
               fetch=True)[0][0]
    print(f"  {city}/buildings: {count} total (city)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase",
                    choices=["places", "segments", "divisions", "buildings", "all"],
                    required=True)
    ap.add_argument("--city", default="all",
                    choices=list(CITIES) + ["all"])
    args = ap.parse_args()

    cities = list(CITIES) if args.city == "all" else [args.city]
    phases = (["places", "segments", "divisions", "buildings"]
              if args.phase == "all" else [args.phase])

    fn_map = {"places": import_places, "segments": import_segments,
              "divisions": import_divisions, "buildings": import_buildings}

    for phase in phases:
        print(f"\n{'='*60}\nPHASE : {phase}\n{'='*60}")
        fn = fn_map[phase]
        for city in cities:
            print(f"\n--- {CITIES[city]['label']} ---")
            fn(city)

    print("\n=== ÉTAT FINAL DB ===")
    for tbl in ("raw_places", "mapnet_edges", "mapnet_divisions", "mapnet_buildings"):
        rows = pg(f"SELECT COALESCE(city,'?'),count(*) FROM {tbl} "
                  f"GROUP BY city ORDER BY city", fetch=True)
        for r in rows:
            print(f"  {tbl:25s} {r[0]:12s} {r[1]}")


if __name__ == "__main__":
    main()
