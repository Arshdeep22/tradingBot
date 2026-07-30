"""Show row counts for every table in trades.db and agent.db."""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILES = [
    os.path.join(ROOT, "database", "trades.db"),
    os.path.join(ROOT, "database", "agent.db"),
]


def inspect(path: str) -> None:
    if not os.path.exists(path):
        print(f"[skip] {path} does not exist")
        return
    print(f"\n=== {os.path.basename(path)} ===")
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]
        max_name = max((len(t) for t in tables), default=10)
        for t in tables:
            try:
                (n,) = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()
            except Exception as e:
                n = f"ERR: {e}"
            marker = "  " if n else "* "  # star empty tables
            print(f"  {marker}{t:<{max_name}}  {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    for db in DB_FILES:
        inspect(db)