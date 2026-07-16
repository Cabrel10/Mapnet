-- ============================================================
-- INITIALISATION POSTGIS - MapNet
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ============================================================
-- TABLE : Utilisateurs / Chauffeurs (Auth Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'driver' CHECK (role IN ('admin', 'driver', 'operator')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================
-- TABLE : Traces GPS brutes (GPS Collect Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS gpx_traces (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(100) NOT NULL,
    chauffeur_id VARCHAR(50) NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    elevation DECIMAL(10, 2),
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    speed_kmh DECIMAL(6, 2),
    bearing DECIMAL(6, 2),
    accuracy_m DECIMAL(6, 2),
    geom geometry(Point, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_latitude CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT valid_longitude CHECK (longitude BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS idx_gpx_traces_geom ON gpx_traces USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_gpx_traces_trace_id ON gpx_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_gpx_traces_chauffeur ON gpx_traces(chauffeur_id);
CREATE INDEX IF NOT EXISTS idx_gpx_traces_recorded_at ON gpx_traces(recorded_at);

-- ============================================================
-- TABLE : Segments de routes (Map Engine Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS mapnet_edges (
    id SERIAL PRIMARY KEY,
    edge_id VARCHAR(100) UNIQUE NOT NULL,
    source_node BIGINT,
    target_node BIGINT,
    name VARCHAR(255),
    highway_type VARCHAR(50),
    surface VARCHAR(50),
    oneway BOOLEAN DEFAULT FALSE,
    max_speed INTEGER,
    length_m DECIMAL(10, 2),
    geom geometry(LineString, 4326),
    status VARCHAR(20) DEFAULT 'osm_existing'
        CHECK (status IN ('osm_existing', 'non_cartographie_osm', 'validated', 'rejected')),
    confirmation_count INTEGER DEFAULT 0,
    first_seen_at TIMESTAMP WITH TIME ZONE,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mapnet_edges_geom ON mapnet_edges USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_mapnet_edges_status ON mapnet_edges(status);
CREATE INDEX IF NOT EXISTS idx_mapnet_edges_highway ON mapnet_edges(highway_type);

-- ============================================================
-- TABLE : Points d'Intérêt (Places Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_places (
    place_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(250) NOT NULL,
    category VARCHAR(50),
    subcategory VARCHAR(100),
    address TEXT,
    phone VARCHAR(50),
    website VARCHAR(255),
    rating DECIMAL(2, 1),
    review_count INTEGER,
    source VARCHAR(50) DEFAULT 'overpass',
    geom geometry(Point, 4326),
    raw_response JSONB,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    validated BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_raw_places_geom ON raw_places USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_raw_places_category ON raw_places(category);

-- ============================================================
-- TABLE : Zones d'exclusion aérienne (CCAA Compliance Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS ccaa_nofly_zones (
    id SERIAL PRIMARY KEY,
    zone_name VARCHAR(255) NOT NULL,
    zone_type VARCHAR(50) NOT NULL
        CHECK (zone_type IN ('airport', 'military', 'government', 'restricted')),
    altitude_max_m INTEGER,
    geom geometry(Polygon, 4326),
    effective_from TIMESTAMP WITH TIME ZONE,
    effective_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ccaa_nofly_zones_geom ON ccaa_nofly_zones USING GIST(geom);

-- ============================================================
-- TABLE : Plans de vol drones (CCAA Compliance Service)
-- ============================================================
CREATE TABLE IF NOT EXISTS drone_flight_plans (
    id SERIAL PRIMARY KEY,
    drone_id VARCHAR(100) NOT NULL,
    operator_id VARCHAR(100) NOT NULL,
    flight_polygon geometry(Polygon, 4326),
    altitude_m INTEGER NOT NULL,
    planned_start TIMESTAMP WITH TIME ZONE NOT NULL,
    planned_end TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'completed')),
    ccaa_reference VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drone_flight_plans_geom ON drone_flight_plans USING GIST(flight_polygon);

-- ============================================================
-- FONCTION : Détection de conflit de vol
-- ============================================================
CREATE OR REPLACE FUNCTION check_flight_zone_conflict()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ccaa_nofly_zones
        WHERE ST_Intersects(NEW.flight_polygon, geom)
        AND (effective_until IS NULL OR effective_until > NOW())
    ) THEN
        RAISE EXCEPTION 'Flight plan intersects with a no-fly zone';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_check_nofly_zone'
    ) THEN
        CREATE TRIGGER trigger_check_nofly_zone
        BEFORE INSERT OR UPDATE ON drone_flight_plans
        FOR EACH ROW EXECUTE FUNCTION check_flight_zone_conflict();
    END IF;
END $$;
