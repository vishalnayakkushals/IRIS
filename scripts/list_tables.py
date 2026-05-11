import sqlite3
from pathlib import Path

for db in ["data/iris.db", "data/exports/store_registry.db"]:
    if Path(db).exists():
        c = sqlite3.connect(db)
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"{db}: {tables}")
        c.close()
