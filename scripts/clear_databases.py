"""Wipe all rows from every table in trades.db and agent.db.

Tables are preserved (schema kept intact) so the app can start fresh
without needing to re-run migrations.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILES = [
    os.path.join(ROOT, "database", "trades.db"),
    os.path.join(ROOT, "database", "agent.db"),
]


def clear_db(path: str) -> None:
    if not os.path.exists(path):
        print(f"[skip] {path} does not exist")
        return
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        if not tables:
            print(f"[ok]   {path}: no tables")
            return
        for t in tables:
            cur.execute(f'DELETE FROM "{t}"')
        # Reset autoincrement counters if present
        try:
            cur.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        # Reclaim space
        conn.execute("VACUUM")
        print(f"[ok]   {path}: cleared {len(tables)} tables -> {tables}")
    finally:
        conn.close()


def main() -> int:
    for db in DB_FILES:
        clear_db(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())