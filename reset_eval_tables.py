import sqlite3
c = sqlite3.connect('docuguard.db')
c.execute("DELETE FROM findings")
c.execute("DELETE FROM documents")
c.commit()
print("Tablas documents y findings vaciadas.")