from histor.config import load_settings
from histor.db import open_backend
s = load_settings()
db = open_backend(s.db_path, s.database_url)
try:
    with db.read() as tx:
        rows = tx.execute("SELECT c.status, count(*) AS n FROM server_cards c GROUP BY c.status ORDER BY n DESC")
        print("STATUS", [(r["status"], r["n"]) for r in rows])
        rows = tx.execute("SELECT t.endpoint FROM server_cards c JOIN targets t ON t.id = c.target_id WHERE c.status = 'absent'")
        for r in rows: print("ABSENT", r["endpoint"])
finally:
    db.close()
