"""Optional demo data:  python seed_demo.py   (run once, after app has created the DB)"""
import sqlite3
from app import DB
c = sqlite3.connect(DB)
c.executemany("INSERT INTO products(sku,name,price,cost,stock) VALUES(?,?,?,?,?)", [("CH-01", "Wooden Chair", 80, 45, 0), ("TB-01", "Dining Table", 250, 140, 0)])
c.executemany("INSERT INTO materials(name,unit,stock,reorder,cost) VALUES(?,?,?,?,?)", [("Timber", "kg", 500, 100, 2.5), ("Screws", "pcs", 80, 200, 0.05)])
c.execute("INSERT INTO customers(name,contact) VALUES('Acme Furnishings','acme@example.com')")
c.execute("INSERT INTO suppliers(name,contact) VALUES('Green Timber Ltd','+91 90000 00000')")
c.commit(); print("Demo data added.")
