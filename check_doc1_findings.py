import sqlite3
c = sqlite3.connect('docuguard.db')
rows = c.execute("""
    SELECT f.finding_type, f.severity, f.source_snippet, f.description
    FROM findings f
    JOIN documents d ON f.document_id = d.id
    WHERE d.doc_id = 'doc-0001'
""").fetchall()
for r in rows:
    print(r)