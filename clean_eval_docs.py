import sqlite3
c = sqlite3.connect('docuguard.db')
c.execute("DELETE FROM findings WHERE document_id IN (SELECT id FROM documents WHERE doc_id LIKE 'doc-%')")
c.execute("DELETE FROM documents WHERE doc_id LIKE 'doc-%'")
c.commit()
print("Limpio.")