import sqlite3
c = sqlite3.connect('docuguard.db')
rows = c.execute("""
    SELECT document_id, finding_type, severity, COUNT(*) as cnt
    FROM findings
    GROUP BY document_id, finding_type, severity
    HAVING cnt > 1
    ORDER BY document_id
""").fetchall()
if not rows:
    print("Sin duplicados exactos. Bug resuelto.")
else:
    print(f"Encontrados {len(rows)} grupos duplicados:")
    for r in rows:
        print(r)