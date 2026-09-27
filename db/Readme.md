# OCM Export → PostgreSQL

Scripts to load the per-POI JSON export from [../data/](../data/) into a relational
PostgreSQL database. See [schema.md](schema.md) for the ER diagram and design notes.

| File | Purpose |
|---|---|
| [schema.sql](schema.sql) | DDL — creates the empty table structure (database-neutral SQL) |
| [import_full.py](import_full.py) | Full import of referencedata.json + all station files |
| [import_update.py](import_update.py) | Incremental update from git history (applies only changed files) |
| [ocm_common.py](ocm_common.py) | Shared JSON→row flattening, used by both scripts |
| [geo.sql](geo.sql) | Optional: enables radius searches (PostgreSQL-specific) |

## Setup

```bash
pip install psycopg2-binary

createdb ocm
psql -d ocm -f db/schema.sql
```

The `--dsn` argument accepts any libpq connection string; if omitted, the standard
`PG*` environment variables (`PGHOST`, `PGDATABASE`, `PGUSER`, …) are used.

## Full import

Whole database (~267k files, all countries):

```bash
python3 db/import_full.py --dsn "dbname=ocm"
```

One country only (e.g. Spain), or several:

```bash
python3 db/import_full.py --dsn "dbname=ocm" --countries ES
python3 db/import_full.py --dsn "dbname=ocm" --countries ES,DE,FR
```

Useful flags:

- `--create-schema` — run schema.sql first (instead of the `psql -f` step above)
- `--truncate` — empty all tables before importing (for a clean re-import)

The import records the current git commit in `import_state.last_commit`,
which the update script uses as its diff base.

## Incremental update (after `git pull` of new data)

Applies only the differences between the last imported commit and `HEAD`,
using `git diff`:

```bash
git pull
python3 db/import_update.py --dsn "dbname=ocm"
```

If the full import was filtered by country, use the same filter:

```bash
python3 db/import_update.py --dsn "dbname=ocm" --countries ES
```

Preview what would change without touching the database:

```bash
python3 db/import_update.py --dsn "dbname=ocm" --dry-run
```

Explicit commit range (instead of `import_state.last_commit` → `HEAD`):

```bash
python3 db/import_update.py --dsn "dbname=ocm" --from HEAD~3 --to HEAD
```

Everything runs in a single transaction; `import_state.last_commit` is advanced
on success, so the update can simply be re-run after a failure.

## Example query

```sql
-- charging stations in the city of Alicante
SELECT id, title, town, latitude, longitude
FROM charge_points
WHERE town IN ('Alicante', 'Alacant', 'Alicante/Alacant', 'Alacant / Alicante');
```

## Geospatial search (radius around a position)

One-time setup — enables the built-in `cube`/`earthdistance` extensions and adds a
GiST index over the existing latitude/longitude columns (no table changes):

```bash
psql -d ocm -f db/geo.sql
```

Find all stations within 5 km of a position, nearest first:

```sql
SELECT id, title, town,
       round(earth_distance(ll_to_earth(38.3452, -0.4810),
                            ll_to_earth(latitude, longitude))) AS meters
FROM charge_points
WHERE earth_box(ll_to_earth(38.3452, -0.4810), 5000)
          @> ll_to_earth(latitude, longitude)   -- fast index-backed bounding box
  AND earth_distance(ll_to_earth(38.3452, -0.4810),
                     ll_to_earth(latitude, longitude)) <= 5000  -- exact circle
ORDER BY meters;
```

For heavier GIS workloads (polygons, exact geodesics, routing) install
[PostGIS](https://postgis.net) instead and index
`ST_MakePoint(longitude, latitude)::geography`, then query with `ST_DWithin`.
