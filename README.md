# MFG360 – Integrated Manufacturing Management Platform (basic release)
Flask + SQLite implementation of the MFG360 SRS: users/roles, master data, orders, production batches,
inventory transactions, quality inspections, expenses, sales, profitability, alerts, dashboard, CSV reports.

## Run
```
python -m venv venv
venv\Scripts\activate        (Windows)   |   source venv/bin/activate   (Mac/Linux)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 — login `admin` / `admin123` (change it). Optional demo data: `python seed_demo.py`.

## Workflow
Customer + Product -> Order -> Production Batch (update produced qty) -> Quality Inspection (accepted units
go to finished stock) -> Order status "Delivered" (deducts stock) -> Sales + Expenses -> Profitability.
Roles: admin, management (read-only), production, quality, inventory, sales, finance.
