import sqlite3

text = open("dataset/evidence/databases/customer_data_inventory_20260905.sql", "r", encoding="utf-8").read()
conn = sqlite3.connect(":memory:")
try:
    conn.executescript(text)
    print("Executed successfully!")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        count = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count} rows")
except Exception as e:
    print("Execution error:", e)
