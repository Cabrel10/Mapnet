-- MAPNET search infrastructure (Cameroon-first unified search)
-- Idempotent. Run against quamtechs_db.
--
-- Enables accent/case-insensitive trigram search over divisions, POI and
-- named buildings, backing services/places /api/v1/places/search.

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- IMMUTABLE normalization wrapper (schema-qualified so it inlines inside
-- functional index definitions regardless of search_path).
CREATE OR REPLACE FUNCTION mapnet_norm(txt text)
RETURNS text
AS $$ SELECT public.unaccent(lower(txt)) $$
LANGUAGE sql IMMUTABLE;

-- Trigram GIN indexes on normalized names -> substring/word search in ms.
CREATE INDEX IF NOT EXISTS idx_places_name_trgm
    ON raw_places USING gin (mapnet_norm(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_div_name_trgm
    ON mapnet_divisions USING gin (mapnet_norm(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_bld_name_trgm
    ON mapnet_buildings USING gin (mapnet_norm(name) gin_trgm_ops);

ANALYZE raw_places;
ANALYZE mapnet_divisions;
ANALYZE mapnet_buildings;

-- ---------------------------------------------------------------------------
-- Building labels: name every possible building either by its own name or by
-- the nearest POI within 25 m. Built POI-first (13.7k rows) for speed, using
-- the native GIST index + bbox prefilter (runs in seconds, vs minutes for a
-- 1.5M-row building-first scan).
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS mapnet_building_labels;
CREATE TABLE mapnet_building_labels AS
SELECT DISTINCT ON (b.building_id)
       b.building_id,
       p.name        AS label,
       'poi'::text   AS label_source,
       p.category    AS poi_category,
       ST_Distance(b.geom::geography, p.geom::geography) AS poi_dist_m,
       b.class, b.city,
       ST_Y(ST_Centroid(b.geom)) AS latitude,
       ST_X(ST_Centroid(b.geom)) AS longitude
FROM raw_places p
JOIN LATERAL (
    SELECT bb.building_id, bb.geom, bb.class, bb.city
    FROM mapnet_buildings bb
    WHERE bb.geom && ST_Expand(p.geom, 0.00025)   -- ~25 m bbox, GIST-indexable
      AND ST_DWithin(bb.geom, p.geom, 0.00025)
    ORDER BY bb.geom <-> p.geom
    LIMIT 1
) b ON TRUE
WHERE p.name IS NOT NULL AND p.name <> ''
ORDER BY b.building_id, (b.geom <-> p.geom);

ALTER TABLE mapnet_building_labels ADD PRIMARY KEY (building_id);
CREATE INDEX IF NOT EXISTS idx_bldlabels_name_trgm
    ON mapnet_building_labels USING gin (mapnet_norm(label) gin_trgm_ops);
ANALYZE mapnet_building_labels;
