#!/usr/bin/env python3
"""Incremental update of the OCM database from git history.

Compares the last imported commit (import_state.last_commit) with HEAD via
`git diff --name-status` and applies only the differences:

  - added/modified OCM-*.json  -> delete + re-insert the charge point
                                  (children removed via ON DELETE CASCADE)
  - deleted OCM-*.json         -> delete the charge point
  - changed referencedata.json -> upsert all reference tables

File contents are read from git (`git show <to>:<path>`), not the working
tree, so the update is exact for the requested commit range. Everything runs
in one transaction; import_state.last_commit is advanced at the end.

Usage:
    python3 db/import_update.py --dsn "postgresql://user:pass@localhost/ocm"
    python3 db/import_update.py --from HEAD~3 --to HEAD   # explicit range

Requires: pip install psycopg2-binary
"""

import argparse
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ocm_common as oc

REPO_ROOT = Path(__file__).resolve().parent.parent


def upsert(cur, table, cols, rows):
    """INSERT ... ON CONFLICT (id) DO UPDATE (Postgres-specific)."""
    if not rows:
        return
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
    execute_values(cur,
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
        f"ON CONFLICT (id) DO UPDATE SET {updates}",
        rows)


def load_ref_ids(cur):
    """Current reference-table IDs from the DB, for dangling-FK checks."""
    tables = {}
    for table in oc.REFERENCE_INSERT_ORDER:
        cur.execute(f"SELECT id FROM {table}")
        tables[table] = cur.fetchall()
    return oc.RefIds(tables)


def update_reference_data(cur, to_ref):
    print("referencedata.json changed -> upserting reference tables")
    ref = oc.git_show_json(REPO_ROOT, to_ref, "data/referencedata.json")
    tables = oc.flatten_reference_data(ref)
    for table in oc.REFERENCE_INSERT_ORDER:
        upsert(cur, table, oc.REFERENCE_TABLE_COLS[table], tables[table])
        print(f"  {table}: {len(tables[table])} rows upserted")


def apply_station_change(cur, ref_ids, status, path, to_ref, users):
    """Apply one A/M/D diff entry for a station file."""
    cp_id = int(Path(path).stem.split("-")[1])           # OCM-<id>.json
    cur.execute("DELETE FROM charge_points WHERE id = %s", (cp_id,))
    if status == "D":
        return
    country_code = Path(path).parent.name
    d = oc.git_show_json(REPO_ROOT, to_ref, path)
    rows = oc.flatten_charge_point(d, country_code, ref_ids)
    for uid, uname in rows.pop("users"):
        users[uid] = uname
    cur.execute(
        f"INSERT INTO charge_points ({', '.join(oc.CHARGE_POINT_COLS)}) "
        f"VALUES ({', '.join(['%s'] * len(oc.CHARGE_POINT_COLS))})",
        rows["charge_points"][0])
    for table, cols in oc.CHILD_TABLE_COLS.items():
        if rows[table]:
            execute_values(cur,
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s",
                rows[table])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", default="", help="Postgres DSN "
                    "(default: PG* environment variables)")
    ap.add_argument("--from", dest="from_ref",
                    help="base commit (default: import_state.last_commit)")
    ap.add_argument("--to", dest="to_ref", default="HEAD",
                    help="target commit (default: HEAD)")
    ap.add_argument("--countries",
                    help="comma-separated ISO2 filter, e.g. ES,DE "
                         "(use the same filter as the full import)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change, don't touch the DB")
    args = ap.parse_args()

    countries = set(args.countries.split(",")) if args.countries else None
    conn = psycopg2.connect(args.dsn)
    try:
        with conn, conn.cursor() as cur:
            from_ref = args.from_ref
            if not from_ref:
                cur.execute(
                    "SELECT value FROM import_state WHERE key = 'last_commit'")
                row = cur.fetchone()
                if not row:
                    sys.exit("no import_state.last_commit found - "
                             "run import_full.py first or pass --from")
                from_ref = row[0]
            to_commit = oc.git_output(
                REPO_ROOT, "rev-parse", args.to_ref).strip()
            print(f"diffing {from_ref[:12]} .. {to_commit[:12]}")

            # --no-renames: a station moving between country folders must
            # appear as D + A, not as an R rename line
            diff = oc.git_output(REPO_ROOT, "diff", "--name-status",
                                 "--no-renames", from_ref, to_commit,
                                 "--", "data/")
            ref_changed = False
            station_changes = []          # (status, path)
            for line in diff.splitlines():
                status, _, path = line.partition("\t")
                if path.endswith("referencedata.json"):
                    ref_changed = True
                elif "OCM-" in path and path.endswith(".json"):
                    if countries and Path(path).parent.name not in countries:
                        continue
                    station_changes.append((status, path))

            n_add = sum(1 for s, _ in station_changes if s == "A")
            n_mod = sum(1 for s, _ in station_changes if s == "M")
            n_del = sum(1 for s, _ in station_changes if s == "D")
            print(f"changes: {n_add} added, {n_mod} modified, {n_del} deleted"
                  f"{', referencedata changed' if ref_changed else ''}")
            if args.dry_run:
                return
            if not station_changes and not ref_changed:
                print("nothing to do")

            if ref_changed:
                update_reference_data(cur, to_commit)

            ref_ids = load_ref_ids(cur)
            users = {}
            for i, (status, path) in enumerate(station_changes, 1):
                apply_station_change(cur, ref_ids, status, path,
                                     to_commit, users)
                if i % 1000 == 0:
                    print(f"  {i}/{len(station_changes)} applied...")

            if users:
                upsert(cur, "users", oc.USER_COLS, sorted(users.items()))

            cur.execute("""
                INSERT INTO import_state (key, value)
                VALUES ('last_commit', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (to_commit,))

            print(f"done: {len(station_changes)} station files applied, "
                  f"import_state.last_commit = {to_commit[:12]}")
            if ref_ids.dangling:
                print("dangling references set to NULL:")
                for (table, value), count in sorted(ref_ids.dangling.items()):
                    print(f"  {table} id={value}: {count}x")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
