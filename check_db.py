import sqlite3
c = sqlite3.connect('docuguard.db')

print("--- Documentos ---")
rows = c.execute("SELECT doc_id, status, risk_level FROM documents WHERE doc_id IN ('doc-0001','doc-0002','doc-0003')").fetchall()
for r in rows:
    print(r)

print("--- Findings ---")
rows2 = c.execute("SELECT document_id, finding_type, severity FROM findings").fetchall()
for r in rows2:
    print(r)