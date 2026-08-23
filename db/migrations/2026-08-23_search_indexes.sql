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
