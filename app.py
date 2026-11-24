"""MFG360 - Integrated Manufacturing Management Platform (basic release).
Flask + SQLite. Run: python app.py  ->  http://127.0.0.1:5000  (admin / admin123)"""
import csv, io, os, sqlite3
from datetime import date
from functools import wraps
from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, Response, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mfg360.db")

ROLES = ["admin", "management", "production", "quality", "inventory", "sales", "finance"]
ORDER_STATUS = ["Pending", "In Production", "Ready", "Delivered", "Cancelled"]
BATCH_STATUS = ["Planned", "In Progress", "Completed", "Delayed"]

# field = (column, label, kind, extra)   kind: text|num|date|select|fk
# 'write' = roles allowed to change data, 'read' = extra roles allowed to view.
# admin can do everything, management can view everything.
MODS = {
 "products": dict(title="Products", write=["production", "sales", "inventory"],
   read=["quality", "finance"], fields=[("sku", "SKU", "text", None), ("name", "Name", "text", None),
   ("price", "Selling price", "num", None), ("cost", "Unit cost", "num", None), ("stock", "Finished stock", "num", None)]),
 "materials": dict(title="Raw Materials", write=["inventory"], read=["production", "finance"],
   fields=[("name", "Name", "text", None), ("unit", "Unit", "text", None), ("stock", "Stock", "num", None),
   ("reorder", "Reorder level", "num", None), ("cost", "Unit cost", "num", None)]),
 "suppliers": dict(title="Suppliers", write=["inventory"], read=[],
   fields=[("name", "Name", "text", None), ("contact", "Contact", "text", None)], optional=["contact"]),
 "customers": dict(title="Customers", write=["sales"], read=["finance"],
   fields=[("name", "Name", "text", None), ("contact", "Contact", "text", None)], optional=["contact"]),
 "orders": dict(title="Customer Orders", write=["sales"], read=["production", "finance"],
   inline=["status"], fields=[("customer_id", "Customer", "fk", "customers"), ("product_id", "Product", "fk", "products"),
   ("qty", "Quantity", "num", None), ("price", "Unit price", "num", None), ("order_date", "Order date", "date", None),
   ("delivery_date", "Delivery date", "date", None), ("status", "Status", "select", ORDER_STATUS)]),
 "batches": dict(title="Production Batches", write=["production"], read=["quality", "sales"],
   inline=["produced_qty", "status"], optional=["order_id"],
   fields=[("product_id", "Product", "fk", "products"), ("order_id", "Order", "fk", "orders"),
   ("planned_qty", "Planned qty", "num", None), ("produced_qty", "Produced qty", "num", None),
   ("planned_date", "Planned date", "date", None), ("responsible", "Responsible", "text", None),
   ("status", "Status", "select", BATCH_STATUS)]),
 "inventory": dict(title="Inventory Transactions", write=["inventory", "production"], read=[], signed=["qty"],
   fields=[("material_id", "Material", "fk", "materials"),
   ("type", "Type", "select", ["Receipt", "Issue", "Consumption", "Adjustment"]),
   ("qty", "Qty (Adjustment may be +/-)", "num", None), ("tx_date", "Date", "date", None), ("note", "Note", "text", None)],
   optional=["note"]),
 "inspections": dict(title="Quality Inspections", write=["quality"], read=["production"], optional=["defects", "action"],
   fields=[("batch_id", "Batch", "fk", "batches"), ("accepted", "Accepted qty", "num", None),
   ("rejected", "Rejected qty", "num", None), ("defects", "Defects", "text", None),
   ("action", "Corrective action", "text", None), ("insp_date", "Date", "date", None)]),
 "expenses": dict(title="Expenses", write=["finance"], read=[], optional=["order_id", "description"],
   fields=[("exp_date", "Date", "date", None), ("category", "Category", "text", None), ("amount", "Amount", "num", None),
   ("order_id", "Order (optional)", "fk", "orders"), ("description", "Description", "text", None)]),
 "sales": dict(title="Sales / Revenue", write=["sales", "finance"], read=[],
   fields=[("order_id", "Order", "fk", "orders"), ("sale_date", "Date", "date", None), ("amount", "Amount", "num", None)]),
 "users": dict(title="Users", write=[], read=[], fields=[("username", "Username", "text", None),
   ("password", "Password", "text", None), ("role", "Role", "select", ROLES)]),
}
LABEL = {"orders": "'Order #'||id", "batches": "'Batch #'||id"}  # others use name


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    con = sqlite3.connect(DB)
    for t, m in MODS.items():
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for c, _, k, _x in m["fields"]:
            cols.append(f"{c} " + {"num": "REAL", "fk": "INTEGER"}.get(k, "TEXT"))
        con.execute(f"CREATE TABLE IF NOT EXISTS {t} ({', '.join(cols)})")
    if not con.execute("SELECT 1 FROM users").fetchone():
        con.execute("INSERT INTO users(username,password,role) VALUES('admin',?,'admin')",
                    (generate_password_hash("admin123"),))
    con.commit()
    con.close()


# ---------- access control ----------
def can(mod, write=False):
    r = session.get("role")
    if r == "admin":
        return True
    if mod == "users":
        return False
    m = MODS[mod]
    if write:
        return r in m["write"]
    return r in m["write"] + m["read"] + ["management"]


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return w


@app.context_processor
def inject():
    return dict(MODS=MODS, can=can, today=date.today().isoformat())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE username=?", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password"], request.form["password"]):
            session.clear()
            session.update(uid=u["id"], user=u["username"], role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- helpers ----------
def fk_map(m):
    out = {}
    for c, _, k, extra in m["fields"]:
        if k == "fk":
            lab = LABEL.get(extra, "name")
            out[c] = {r["id"]: r["l"] for r in db().execute(f"SELECT id, {lab} AS l FROM {extra}")}
    return out


def alerts():
    d, today = db(), date.today().isoformat()
    a = []
    for r in d.execute("SELECT name,stock,reorder,unit FROM materials WHERE stock<=reorder"):
        a.append(("Low stock", f"{r['name']}: {r['stock']:g} {r['unit']} left (reorder level {r['reorder']:g})"))
    for r in d.execute("SELECT id,planned_date FROM batches WHERE planned_date<? AND status!='Completed'", (today,)):
        a.append(("Delayed production", f"Batch #{r['id']} was planned for {r['planned_date']}"))
    for r in d.execute("SELECT id,delivery_date FROM orders WHERE delivery_date<? AND status NOT IN ('Delivered','Cancelled')", (today,)):
        a.append(("Overdue order", f"Order #{r['id']} was due {r['delivery_date']}"))
    for r in d.execute("SELECT batch_id, SUM(rejected) rj, SUM(accepted+rejected) t FROM inspections GROUP BY batch_id HAVING t>0 AND rj*1.0/t>0.1"):
        a.append(("Quality problem", f"Batch #{r['batch_id']} rejection rate {100*r['rj']/r['t']:.0f}%"))
    return a


def finance():
    d = db()
    rev = d.execute("SELECT COALESCE(SUM(amount),0) v FROM sales").fetchone()["v"]
    exp = d.execute("SELECT COALESCE(SUM(amount),0) v FROM expenses").fetchone()["v"]
    rows = d.execute("""SELECT o.id, c.name customer, p.name product, o.qty, o.status,
        COALESCE((SELECT SUM(amount) FROM sales WHERE order_id=o.id),0) revenue,
        COALESCE((SELECT SUM(amount) FROM expenses WHERE order_id=o.id),0) expenses,
        o.qty*p.cost est_cost FROM orders o JOIN customers c ON c.id=o.customer_id
        JOIN products p ON p.id=o.product_id ORDER BY o.id DESC""").fetchall()
    return rev, exp, rows


# ---------- pages ----------
@app.route("/")
@login_required
def dashboard():
    d = db()
    q = lambda s: d.execute(s).fetchone()[0]
    rev, exp, _ = finance()
    k = {"Revenue": f"{rev:,.2f}", "Expenses": f"{exp:,.2f}", "Profit": f"{rev-exp:,.2f}",
         "Pending orders": q("SELECT COUNT(*) FROM orders WHERE status IN ('Pending','In Production','Ready')"),
         "Active batches": q("SELECT COUNT(*) FROM batches WHERE status IN ('Planned','In Progress','Delayed')"),
         "Finished goods units": f"{q('SELECT COALESCE(SUM(stock),0) FROM products'):g}",
         "Low-stock materials": q("SELECT COUNT(*) FROM materials WHERE stock<=reorder")}
    return render_template("dashboard.html", k=k, alerts=alerts(), rev=rev, exp=exp)


@app.route("/m/<mod>")
@login_required
def listing(mod):
    m = MODS.get(mod) or abort(404)
    if not can(mod):
        abort(403)
    rows = db().execute(f"SELECT * FROM {mod} ORDER BY id DESC").fetchall()
    return render_template("list.html", mod=mod, m=m, rows=rows, fk=fk_map(m), canw=can(mod, True),
                           roles=ROLES)


@app.route("/m/<mod>/add", methods=["POST"])
@login_required
def add(mod):
    m = MODS.get(mod) or abort(404)
    if not can(mod, True):
        abort(403)
    vals, opt = {}, m.get("optional", [])
    try:
        for c, label, k, extra in m["fields"]:
            v = request.form.get(c, "").strip()
            if not v:
                if c in opt or (mod == "sales" and c == "amount") or (mod == "products" and c == "stock") \
                        or (mod == "materials" and c == "stock") or (mod == "batches" and c == "produced_qty"):
                    vals[c] = None
                    continue
                raise ValueError(f"{label} is required.")
            if k == "num":
                v = float(v)
                if v < 0 and c not in m.get("signed", []):
                    raise ValueError(f"{label} cannot be negative.")
            elif k == "fk":
                v = int(v)
            vals[c] = v
        con = db()
        hook(mod, vals, con)
        cols = ",".join(vals)
        con.execute(f"INSERT INTO {mod}({cols}) VALUES({','.join('?'*len(vals))})", list(vals.values()))
        con.commit()
        flash("Saved.", "ok")
    except ValueError as e:
        db().rollback()
        flash(str(e), "error")
    except sqlite3.IntegrityError:
        db().rollback()
        flash("Duplicate or invalid data.", "error")
    return redirect(url_for("listing", mod=mod))


def hook(mod, v, con):
    """Business rules run before an insert."""
    if mod == "users":
        if not v["password"] or len(v["password"]) < 6:
            raise ValueError("Password must be at least 6 characters.")
        v["password"] = generate_password_hash(v["password"])
    for c in ("stock", "produced_qty"):
        if c in v and v[c] is None:
            v[c] = 0
    if mod == "orders" and v["delivery_date"] < v["order_date"]:
        raise ValueError("Delivery date cannot be before order date.")
    if mod == "inventory":
        q, t = v["qty"], v["type"]
        delta = -abs(q) if t in ("Issue", "Consumption") else (abs(q) if t == "Receipt" else q)
        cur = con.execute("SELECT stock FROM materials WHERE id=?", (v["material_id"],)).fetchone()["stock"]
        if cur + delta < 0:
            raise ValueError(f"Insufficient stock (available {cur:g}).")
        con.execute("UPDATE materials SET stock=stock+? WHERE id=?", (delta, v["material_id"]))
    if mod == "inspections":
        b = con.execute("SELECT * FROM batches WHERE id=?", (v["batch_id"],)).fetchone()
        done = con.execute("SELECT COALESCE(SUM(accepted+rejected),0) s FROM inspections WHERE batch_id=?",
                           (v["batch_id"],)).fetchone()["s"]
        if v["accepted"] + v["rejected"] <= 0:
            raise ValueError("Enter accepted or rejected quantity.")
        if done + v["accepted"] + v["rejected"] > b["produced_qty"]:
            raise ValueError(f"Inspected quantity exceeds produced quantity ({b['produced_qty']:g}).")
        con.execute("UPDATE products SET stock=stock+? WHERE id=?", (v["accepted"], b["product_id"]))
    if mod == "sales" and v["amount"] is None:
        o = con.execute("SELECT qty*price a FROM orders WHERE id=?", (v["order_id"],)).fetchone()
        v["amount"] = o["a"]


@app.route("/m/<mod>/<int:rid>/update", methods=["POST"])
@login_required
def update(mod, rid):
    m = MODS.get(mod) or abort(404)
    if not can(mod, True) or "inline" not in m:
        abort(403)
    con = db()
    row = con.execute(f"SELECT * FROM {mod} WHERE id=?", (rid,)).fetchone() or abort(404)
    try:
        sets = {}
        for c in m["inline"]:
            if c in request.form:
                v = request.form[c]
                sets[c] = float(v) if c == "produced_qty" else v
        if "produced_qty" in sets and sets["produced_qty"] < 0:
            raise ValueError("Quantity cannot be negative.")
        if mod == "orders" and sets.get("status") == "Delivered" and row["status"] != "Delivered":
            st = con.execute("SELECT stock FROM products WHERE id=?", (row["product_id"],)).fetchone()["stock"]
            if st < row["qty"]:
                raise ValueError(f"Not enough finished stock to deliver (have {st:g}, need {row['qty']:g}).")
            con.execute("UPDATE products SET stock=stock-? WHERE id=?", (row["qty"], row["product_id"]))
        if mod == "batches" and sets.get("status") == "Completed" and \
                (sets.get("produced_qty", row["produced_qty"]) or 0) <= 0:
            raise ValueError("Enter produced quantity before completing a batch.")
        con.execute(f"UPDATE {mod} SET {','.join(c+'=?' for c in sets)} WHERE id=?", [*sets.values(), rid])
        con.commit()
        flash("Updated.", "ok")
    except ValueError as e:
        con.rollback()
        flash(str(e), "error")
    return redirect(url_for("listing", mod=mod))


@app.route("/m/<mod>/<int:rid>/delete", methods=["POST"])
@login_required
def delete(mod, rid):
    if mod not in MODS or not can(mod, True) or mod in ("inventory", "inspections", "users"):
        abort(403)  # transaction history is kept for audit
    try:
        db().execute(f"DELETE FROM {mod} WHERE id=?", (rid,))
        db().commit()
        flash("Deleted.", "ok")
    except sqlite3.IntegrityError:
        flash("Cannot delete: record is used elsewhere.", "error")
    return redirect(url_for("listing", mod=mod))


@app.route("/users/<int:rid>/delete", methods=["POST"])
@login_required
def delete_user(rid):
    if session.get("role") != "admin" or rid == session["uid"]:
        abort(403)
    db().execute("DELETE FROM users WHERE id=?", (rid,))
    db().commit()
    return redirect(url_for("listing", mod="users"))


@app.route("/profitability")
@login_required
def profitability():
    if session["role"] not in ("admin", "management", "finance"):
        abort(403)
    rev, exp, rows = finance()
    return render_template("profit.html", rev=rev, exp=exp, rows=rows)


@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html", names=[t for t in MODS if t != "users" and can(t)])


@app.route("/export/<name>.csv")
@login_required
def export(name):
    out = io.StringIO()
    w = csv.writer(out)
    if name == "profitability":
        if session["role"] not in ("admin", "management", "finance"):
            abort(403)
        _, _, rows = finance()
        w.writerow(rows[0].keys() if rows else ["no data"])
        w.writerows([tuple(r) for r in rows])
    else:
        if name not in MODS or name == "users" or not can(name):
            abort(403)
        cur = db().execute(f"SELECT * FROM {name}")
        w.writerow([c[0] for c in cur.description])
        w.writerows([tuple(r) for r in cur.fetchall()])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


init_db()
if __name__ == "__main__":
    app.run(debug=True)
