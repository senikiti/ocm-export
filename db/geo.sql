-- Optional geospatial support for radius searches ("stations within 5 km").
-- PostgreSQL-specific (kept out of the database-neutral schema.sql).
--
-- Uses the built-in contrib extensions cube + earthdistance: no table changes,
-- just a functional GiST index over the existing latitude/longitude columns.
--
--   psql -d ocm -f db/geo.sql
--
-- For heavier GIS needs (polygons, routing, exact geodesics) install PostGIS
-- instead and index ST_MakePoint(longitude, latitude)::geography.

CREATE EXTENSION IF NOT EXISTS cube;
CREATE EXTENSION IF NOT EXISTS earthdistance;

CREATE INDEX IF NOT EXISTS idx_charge_points_earth
    ON charge_points USING gist (ll_to_earth(latitude, longitude));

-- ----------------------------------------------------------------------
-- Example: all charging stations within 5 km of a position, nearest first
-- (earth_box() is a fast index-backed bounding box; the earth_distance()
--  condition trims the box corners to the exact circle)
-- ----------------------------------------------------------------------
-- SELECT id, title, town,
--        round(earth_distance(ll_to_earth(38.3452, -0.4810),
--                             ll_to_earth(latitude, longitude))) AS meters
-- FROM charge_points
-- WHERE earth_box(ll_to_earth(38.3452, -0.4810), 5000)
--           @> ll_to_earth(latitude, longitude)
--   AND earth_distance(ll_to_earth(38.3452, -0.4810),
--                      ll_to_earth(latitude, longitude)) <= 5000
-- ORDER BY meters;
