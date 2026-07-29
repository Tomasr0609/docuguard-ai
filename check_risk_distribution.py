import sqlite3
c = sqlite3.connect('docuguard.db')
print(c.execute("SELECT risk_level, COUNT(*) FROM documents GROUP BY risk_level").fetchall())