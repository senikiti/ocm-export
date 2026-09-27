#!/usr/bin/env python3
"""Full import of the OCM export into Postgres.

Loads data/referencedata.json into the reference tables, then bulk-loads every
data/<CC>/OCM-*.json station file via COPY. Records the current git commit in
import_state so import_update.py knows its diff base.

Usage:
    python3 db/import_full.py --dsn "postgresql://user:pass@localhost/ocm"
    python3 db/import_full.py --countries ES,DE --truncate

The DSN can also come from standard PG* environment variables (PGHOST,
PGDATABASE, ...). Requires: pip install psycopg2-binary

Run db/schema.sql first to create the tables (or pass --create-schema).
"""

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ocm_common as oc

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

BATCH_SIZE = 5000  # station files per COPY batch


# ------------------------------------------------------------------ COPY I/O

def copy_rows(cur, table, cols, rows):
    """Bulk-load row tuples via COPY FROM STDIN (csv format)."""
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(["\\N" if v is None else v for v in row])
    buf.seek(0)
    cur.copy_expert(
        f"COPY {table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
        buf,
    )


# ------------------------------------------------------------------- import

def import_reference_data(cur):
    ref = json.loads((DATA_DIR / "referencedata.json").read_text())
    tables = oc.flatten_reference_data(ref)
    for table in oc.REFERENCE_INSERT_ORDER:
        copy_rows(cur, table, oc.REFERENCE_TABLE_COLS[table], tables[table])
        print(f"  {table}: {len(tables[table])} rows")
    return oc.RefIds(tables)


def iter_station_files(countries=None):
    for cc_dir in sorted(DATA_DIR.iterdir()):
        if not cc_dir.is_dir():
            continue
        if countries and cc_dir.name not in countries:
            continue
        for f in sorted(cc_dir.glob("OCM-*.json")):
            yield cc_dir.name, f


def import_stations(cur, ref_ids, countries=None):
    buffers = {t: [] for t in ("charge_points", *oc.CHILD_TABLE_COLS)}
    users = {}          # id -> username (dedup across all files)
    totals = {t: 0 for t in buffers}
    n_files = 0
    started = time.time()

    def flush():
        copy_rows(cur, "charge_points", oc.CHARGE_POINT_COLS,
                  buffers["charge_points"])
        for t, cols in oc.CHILD_TABLE_COLS.items():
            copy_rows(cur, t, cols, buffers[t])
        for t in buffers:
            totals[t] += len(buffers[t])
            buffers[t].clear()

    for country_code, path in iter_station_files(countries):
        try:
            d = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"  SKIP {path}: {e}", file=sys.stderr)
            continue
        rows = oc.flatten_charge_point(d, country_code, ref_ids)
        for uid, uname in rows.pop("users"):
            users[uid] = uname
        for t, r in rows.items():
            buffers[t].extend(r)
        n_files += 1
        if len(buffers["charge_points"]) >= BATCH_SIZE:
            flush()
            print(f"  {n_files} files... ({time.time() - started:.0f}s)")
    flush()

    copy_rows(cur, "users", oc.USER_COLS, sorted(users.items()))
    totals["users"] = len(users)
    print(f"  {n_files} station files imported in {time.time() - started:.0f}s")
    return totals


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", default="", help="Postgres DSN "
                    "(default: PG* environment variables)")
    ap.add_argument("--countries", help="comma-separated ISO2 filter, e.g. ES,DE")
    ap.add_argument("--truncate", action="store_true",
                    help="truncate all tables before import")
    ap.add_argument("--create-schema", action="store_true",
                    help="run db/schema.sql first")
    args = ap.parse_args()

    countries = set(args.countries.split(",")) if args.countries else None
    conn = psycopg2.connect(args.dsn)
    try:
        with conn, conn.cursor() as cur:
            if args.create_schema:
                cur.execute((Path(__file__).parent / "schema.sql").read_text())
                print("schema created")
            if args.truncate:
                cur.execute("""
                    TRUNCATE charge_points, connections, user_comments,
                        media_items, metadata_values, users,
                        metadata_field_options, metadata_fields,
                        metadata_groups, data_types, checkin_status_types,
                        user_comment_types, current_types, charger_types,
                        connection_types, submission_status_types,
                        status_types, usage_types, data_providers,
                        data_provider_status_types, operators, countries,
                        import_state CASCADE""")
                print("tables truncated")

            print("importing reference data...")
            ref_ids = import_reference_data(cur)

            print("importing stations...")
            totals = import_stations(cur, ref_ids, countries)

            # remember the commit this import corresponds to
            commit = oc.git_output(REPO_ROOT, "rev-parse", "HEAD").strip()
            cur.execute("DELETE FROM import_state WHERE key = 'last_commit'")
            cur.execute("INSERT INTO import_state (key, value) VALUES (%s, %s)",
                        ("last_commit", commit))

            print("\nsummary:")
            for t, n in totals.items():
                print(f"  {t}: {n} rows")
            if ref_ids.dangling:
                print("\ndangling references set to NULL:")
                for (table, value), count in sorted(ref_ids.dangling.items()):
                    print(f"  {table} id={value}: {count}x")
            print(f"\nimport_state.last_commit = {commit}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
