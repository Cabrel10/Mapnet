-- MAPNET — enrich raw_places for category search + opening hours (2026-08-24)
--
-- Adds columns needed by the new places endpoints:
--   /api/v1/places/categories, /by-category, /status
-- opening_hours uses the OSM format (e.g. "Mo-Fr 08:00-18:00; Sa 09:00-13:00").
-- These columns are nullable; endpoints degrade gracefully to is_open=null
-- ("unknown") until the data is enriched by a scraper pass.

ALTER TABLE raw_places ADD COLUMN IF NOT EXISTS opening_hours TEXT;
ALTER TABLE raw_places ADD COLUMN IF NOT EXISTS description   TEXT;

-- Case-insensitive category filtering (idx used by /by-category & /categories).
CREATE INDEX IF NOT EXISTS idx_raw_places_category_lower
    ON raw_places (lower(category));

-- Partial index for "open now" style filtering once opening_hours is populated.
CREATE INDEX IF NOT EXISTS idx_raw_places_opening_hours
    ON raw_places (opening_hours)
    WHERE opening_hours IS NOT NULL;
