-- MAPNET — Offline-first synchronisation layer (server side).
-- Additive migration: prepares versioned delta transmission for mobile clients.
-- Git-like model: each dataset has a monotonic version; clients pull only deltas
-- newer than the version they already hold. No full download, ever.
--
-- Apply: psql -h 127.0.0.1 -U postgres -d quamtechs_db -f scripts/init-sync.sql

-- ---------------------------------------------------------------------------
-- 1. Global monotonic version counter, one row per dataset.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_dataset_version (
    dataset      TEXT PRIMARY KEY,          -- 'map','road','poi','ccaa','traffic'
    version      BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO sync_dataset_version(dataset, version) VALUES
    ('map',0),('road',0),('poi',0),('ccaa',0),('traffic',0)
ON CONFLICT (dataset) DO NOTHING;

-- Atomically bump and return the next version for a dataset.
CREATE OR REPLACE FUNCTION sync_next_version(p_dataset TEXT)
RETURNS BIGINT AS $$
DECLARE v BIGINT;
BEGIN
    UPDATE sync_dataset_version
        SET version = version + 1, updated_at = now()
        WHERE dataset = p_dataset
        RETURNING version INTO v;
    IF v IS NULL THEN
        INSERT INTO sync_dataset_version(dataset, version) VALUES (p_dataset, 1)
            RETURNING version INTO v;
    END IF;
    RETURN v;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 2. Per-edge version + soft delete, so deltas can express add/modify/delete.
-- ---------------------------------------------------------------------------
ALTER TABLE mapnet_edges ADD COLUMN IF NOT EXISTS version    BIGINT NOT NULL DEFAULT 0;
ALTER TABLE mapnet_edges ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_mapnet_edges_version ON mapnet_edges(version);

-- ---------------------------------------------------------------------------
-- 3. Change log: append-only record of every edge mutation, for delta replay
--    and audit. change_type: 'A' add, 'M' modify, 'D' delete.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_edge_changelog (
    id          BIGSERIAL PRIMARY KEY,
    edge_id     TEXT NOT NULL,
    version     BIGINT NOT NULL,
    change_type CHAR(1) NOT NULL CHECK (change_type IN ('A','M','D')),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_changelog_version ON sync_edge_changelog(version);

-- ---------------------------------------------------------------------------
-- 4. Trigger: every INSERT/UPDATE of an edge stamps a new map version and
--    appends a changelog row. This is what makes deltas cheap and exact.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_mapnet_edges_version()
RETURNS TRIGGER AS $$
DECLARE v BIGINT; ct CHAR(1);
BEGIN
    v := sync_next_version('map');
    NEW.version := v;
    NEW.updated_at := now();
    IF TG_OP = 'INSERT' THEN
        ct := 'A';
    ELSIF NEW.is_deleted AND NOT OLD.is_deleted THEN
        ct := 'D';
    ELSE
        ct := 'M';
    END IF;
    INSERT INTO sync_edge_changelog(edge_id, version, change_type)
        VALUES (NEW.edge_id, v, ct);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS mapnet_edges_versioning ON mapnet_edges;
CREATE TRIGGER mapnet_edges_versioning
    BEFORE INSERT OR UPDATE ON mapnet_edges
    FOR EACH ROW EXECUTE FUNCTION trg_mapnet_edges_version();

-- ---------------------------------------------------------------------------
-- 5. Tile intelligence: track which tiles change, to prioritise sync.
--    z/x/y = tile coords; change_count drives sync frequency (hot vs cold).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_tile_stats (
    z            INTEGER NOT NULL,
    x            INTEGER NOT NULL,
    y            INTEGER NOT NULL,
    change_count BIGINT NOT NULL DEFAULT 0,
    last_changed TIMESTAMPTZ,
    PRIMARY KEY (z,x,y)
);
