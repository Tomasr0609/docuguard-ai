import sqlite3
c = sqlite3.connect('docuguard.db')
rows = c.execute("SELECT doc_id, risk_level, risk_score FROM documents ORDER BY risk_score").fetchall()
for r in rows:
    print(r)