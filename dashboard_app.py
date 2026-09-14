# -*- coding: utf-8 -*-
"""Dashboard web local (Flask). Lee del cache SQLite; NO consulta Odoo en cada vista.

Arranque:
    python dashboard_app.py
    abrir http://127.0.0.1:8080
"""
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request, send_file

import store
import monthly_pdf

BASE = Path(__file__).parent


def load_config():
    with open(BASE / "config.json", encoding="utf-8") as f:
        return json.load(f)


cfg = load_config()
app = Flask(__name__)
tz = ZoneInfo(cfg.get("timezone", "America/Caracas"))


def build_daily_panel(day: date):
    """Tabla diaria por ejecutivo."""
    execs = store.get_executives(cfg["sqlite_path"])
    touched = {r["odoo_uid"]: r["count"] for r in
               store.get_touched_daily_range(cfg["sqlite_path"], day, day)}
    created = {r["odoo_uid"]: r["count"] for r in
               store.get_created_daily_range(cfg["sqlite_path"], day, day)}
    tienda = {r["odoo_uid"]: r["count"] for r in
              store.get_store_contacts_range(cfg["sqlite_path"], day, day)}

    rows = []
    total = {"creados": 0, "atendidos": 0, "tienda": 0, "total": 0}
    for e in execs:
        c = created.get(e["odoo_uid"], 0)
        t = touched.get(e["odoo_uid"], 0)
        s = tienda.get(e["odoo_uid"], 0)
        total["creados"] += c
        total["atendidos"] += t
        total["tienda"] += s
        total["total"] += c + t + s
        rows.append({"nombre": e["name"], "uid": e["odoo_uid"], "creados": c,
                     "atendidos": t, "tienda": s, "total": c + t + s})
    return rows, total


def build_funnel(day: date):
    """Embudo del dia: etapa x ejecutivo."""
    execs = store.get_executives(cfg["sqlite_path"])
    snap = {(r["odoo_uid"], r["stage"]): r["count"] for r in
            store.get_funnel_snapshot(cfg["sqlite_path"], day)}
    # contacto tienda se suma desde el contador local del dia
    tienda = {r["odoo_uid"]: r["count"] for r in
              store.get_store_contacts_range(cfg["sqlite_path"], day, day)}

    stages = cfg.get("funnel_stages", [])
    header = ["Ejecutivo"] + stages
    rows = []
    totals = {st: 0 for st in stages}
    for e in execs:
        row = {"nombre": e["name"], "uid": e["odoo_uid"]}
        for st in stages:
            v = snap.get((e["odoo_uid"], st), 0)
            if st == "Contacto Tienda" and not v:
                v = tienda.get(e["odoo_uid"], 0)
            row[st] = sum if isinstance(v, list) else v if isinstance(v, int) else (v or 0)
            if isinstance(row[st], int):
                totals[st] += row[st]
        rows.append(row)
    return header, rows, totals


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data", methods=["GET"])
def api_data():
    day = date.today()
    d = request.args.get("day")
    if d:
        try:
            day = date.fromisoformat(d)
        except ValueError:
            day = date.today()
    daily, daily_total = build_daily_panel(day)
    header, funnel_rows, funnel_total = build_funnel(day)
    if not store.last_snapshot_date(cfg["sqlite_path"]):
        funnel_rows = []
    last_sync = store.last_sync_ok(cfg["sqlite_path"])
    return jsonify({
        "dia": day.isoformat(),
        "daily": daily,
        "daily_total": daily_total,
        "funnel_header": header,
        "funnel_rows": funnel_rows,
        "funnel_total": funnel_total,
        "last_sync": last_sync,
    })


@app.route("/api/store_contact", methods=["POST"])
def api_store_contact():
    body = request.get_json(force=True)
    day = date.fromisoformat(body["day"])
    uid = int(body["odoo_uid"])
    delta = int(body.get("delta", 1))
    new_count = store.increment_store_contact(cfg["sqlite_path"], day, uid, delta)
    return jsonify({"ok": True, "odoo_uid": uid, "count": new_count})


@app.route("/api/pdf", methods=["GET"])
def api_pdf():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    tyear, tmonth = month.split("-")
    path = monthly_pdf.generate_monthly_pdf(cfg, int(tyear), int(tmonth))
    return send_file(path, as_attachment=True,
                     download_name=Path(path).name, mimetype="application/pdf")


if __name__ == "__main__":
    print("Dashboard: http://127.0.0.1:8080")
    app.run(host="127.0.0.1", port=8080, debug=False)