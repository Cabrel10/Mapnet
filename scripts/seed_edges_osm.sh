#!/bin/bash
# Seed mapnet_edges avec les routes OSM reelles (zone Yaounde 3.84,11.48 - 3.90,11.56)
# Usage: ./scripts/seed_edges_osm.sh [database]
set -e
DB="${1:-quamtechs_db}"
echo "[1/3] Telechargement Overpass OSM..."
curl -s --max-time 60 "https://overpass-api.de/api/interpreter" \
  --data-urlencode 'data=[out:json][timeout:50];way["highway"](3.84,11.48,3.90,11.56);out tags geom 500;' \
  -o /tmp/osm_yaounde.json
echo "[2/3] Generation SQL..."
python3 - << 'PYEOF'
import json
d = json.load(open('/tmp/osm_yaounde.json'))
ways = [e for e in d.get('elements',[]) if e.get('type')=='way' and e.get('geometry') and len(e['geometry'])>=2]
lines = []
for w in ways:
    t = w.get('tags', {})
    hw = t.get('highway','unclassified').replace("'","''")
    name = t.get('name','').replace("'","''")
    oneway = 'TRUE' if t.get('oneway') in ('yes','true','1') else 'FALSE'
    coords = ", ".join(f"ST_MakePoint({p['lon']}, {p['lat']})" for p in w['geometry'])
    name_sql = f"'{name}'" if name else 'NULL'
    lines.append(
        f"INSERT INTO mapnet_edges (edge_id, name, highway_type, oneway, geom, status, confirmation_count, first_seen_at, last_seen_at, length_m) "
        f"SELECT 'osm-way-{w['id']}', {name_sql}, '{hw}', {oneway}, g.geom, 'osm_existing', 1, now(), now(), "
        f"ST_Length(g.geom::geography) FROM (SELECT ST_SetSRID(ST_MakeLine(ARRAY[{coords}]), 4326) AS geom) g "
        f"ON CONFLICT (edge_id) DO NOTHING;")
open('/tmp/osm_import.sql','w').write("\n".join(lines))
print(f"  {len(lines)} ways")
PYEOF
echo "[3/3] Import dans $DB..."
sudo -u postgres psql -d "$DB" -f /tmp/osm_import.sql > /dev/null
sudo -u postgres psql -d "$DB" -t -c "SELECT 'edges totales: ' || count(*) FROM mapnet_edges;"
