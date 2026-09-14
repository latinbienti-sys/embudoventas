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


def _active_execs():
    """Solo ejecutivos activos configurados (whitelist executives_active)."""
    exclude = {store.normalize(e) for e in cfg.get("executives_exclude", [])}
    active = [store.normalize(e) for e in cfg.get("executives_active", [])]
    execs = [e for e in store.get_executives(cfg["sqlite_path"])
             if store.normalize(e["name"]) not in exclude]
    if active:
        execs = [e for e in execs
                 if any(t in store.normalize(e["name"]) or store.normalize(e["name"]) in t
                        for t in active)]
    return execs


def build_daily_panel(day: date):
    """Tabla diaria por ejecutivo."""
    execs = _active_execs()
    touched = {r["odoo_uid"]: r["count"] for r in
               store.get_touched_daily_range(cfg["sqlite_path"], day, day)}
    created = {r["odoo_uid"]: r["count"] for r in
               store.get_created_daily_range(cfg["sqlite_path"], day, day)}
    boton = {r["odoo_uid"]: r["count"] for r in
             store.get_store_contacts_range(cfg["sqlite_path"], day, day)}
    puerta = {r["odoo_uid"]: r["count"] for r in
              store.get_puerta_daily_range(cfg["sqlite_path"], day, day)}
    actividades = {r["odoo_uid"]: r["count"] for r in
                   store.get_activities_daily_range(cfg["sqlite_path"], day, day)}

    rows = []
    total = {"creados": 0, "atendidos": 0, "tienda": 0, "actividades": 0, "total": 0}
    for e in execs:
        c = created.get(e["odoo_uid"], 0)
        t = touched.get(e["odoo_uid"], 0)
        s = boton.get(e["odoo_uid"], 0) + puerta.get(e["odoo_uid"], 0)
        a = actividades.get(e["odoo_uid"], 0)
        total["creados"] += c
        total["atendidos"] += t
        total["tienda"] += s
        total["actividades"] += a
        total["total"] += c + t + s
        rows.append({"nombre": e["name"], "uid": e["odoo_uid"], "creados": c,
                     "atendidos": t, "tienda": s, "actividades": a, "total": c + t + s})
    return rows, total


def build_funnel(day: date):
    """Embudo del MES (flujo): movimientos por etapa desde el dia seleccionado."""
    execs = _active_execs()
    month_start = day.replace(day=1)
    month_end = month_start.replace(day=28) + timedelta(days=4)
    month_end = month_end - timedelta(days=month_end.day)

    moves = {(r["odoo_uid"], r["stage"]): r["count"] for r in
             store.get_stage_moves_month(cfg["sqlite_path"], day.year, day.month)}
    tienda = {}
    for r in store.get_store_contacts_range(cfg["sqlite_path"], month_start, month_end):
        tienda[r["odoo_uid"]] = tienda.get(r["odoo_uid"], 0) + r["count"]
    for r in store.get_puerta_daily_range(cfg["sqlite_path"], month_start, month_end):
        tienda[r["odoo_uid"]] = tienda.get(r["odoo_uid"], 0) + r["count"]
    actividades = {}
    for r in store.get_activities_daily_range(cfg["sqlite_path"], month_start, month_end):
        actividades[r["odoo_uid"]] = actividades.get(r["odoo_uid"], 0) + r["count"]

    stages = cfg.get("funnel_stages", [])
    header = ["Ejecutivo"] + stages
    rows = []
    totals = {st: 0 for st in stages}
    for e in execs:
        row = {"nombre": e["name"], "uid": e["odoo_uid"]}
        for st in stages:
            if st == "Contacto Tienda":
                v = tienda.get(e["odoo_uid"], 0)
            elif st == "Seguimiento whatsapp Corporativo":
                v = actividades.get(e["odoo_uid"], 0)
            else:
                v = moves.get((e["odoo_uid"], st), 0)
            v = v or 0
            row[st] = v
            totals[st] += v
        rows.append(row)
    return header, rows, totals


def build_gestion(day: date):
    """Gestion diaria: meta vs logrado (flujo de HOY) vs pendiente por ejecutivo."""
    execs = _active_execs()
    stages = cfg.get("funnel_stages", [])
    meta = cfg.get("daily_meta", {}) or {st: 0 for st in stages}
    daily = {r["uid"]: r for r in build_daily_panel(day)[0]}
    moves_hoy = {}
    for r in store.get_stage_moves_range(cfg["sqlite_path"], day, day):
        moves_hoy.setdefault(r["odoo_uid"], {})[r["stage"]] = r["count"]

    rows = []
    totals = {st: {"meta": 0, "logrado": 0, "pendiente": 0} for st in stages}
    for e in execs:
        dr = daily.get(e["odoo_uid"])
        logrado = {}
        for st in stages:
            if st == "Contacto Tienda":
                v = dr["tienda"] if dr else 0
            elif st == "Seguimiento whatsapp Corporativo":
                v = dr["actividades"] if dr else 0
            else:
                v = (moves_hoy.get(e["odoo_uid"], {}) or {}).get(st, 0)
            logrado[st] = v or 0
        m = {st: int(meta.get(st, 0)) for st in stages}
        pend = {st: max(0, m[st] - logrado[st]) for st in stages}
        ok = {st: logrado[st] >= m[st] for st in stages}
        rows.append({"nombre": e["name"], "uid": e["odoo_uid"], "meta": m,
                     "logrado": logrado, "pendiente": pend, "ok": ok})
        for st in stages:
            totals[st]["meta"] += m[st]
            totals[st]["logrado"] += logrado[st]
            totals[st]["pendiente"] += pend[st]

    ventas_uid, venta_mes = store.get_ventas_month(cfg["sqlite_path"], day.year, day.month)
    meta_venta = cfg.get("sales_meta", 0) or 0
    return {
        "stages": stages,
        "rows": rows,
        "totals": totals,
        "ventas": {"meta": meta_venta, "logrado": venta_mes,
                   "pendiente": max(0, meta_venta - venta_mes)},
    }


def build_vista(day: date):
    """Vista por ejecutivo (como el PDF del mes): embudo + diario + venta."""
    execs = _active_execs()
    stages = cfg.get("funnel_stages", [])
    month_start = day.replace(day=1)
    month_end = month_start.replace(day=28) + timedelta(days=4)
    month_end = month_end - timedelta(days=month_end.day)

    moves = {}
    for r in store.get_stage_moves_month(cfg["sqlite_path"], day.year, day.month):
        moves.setdefault(r["odoo_uid"], {})[r["stage"]] = r["count"]
    tienda, act = {}, {}
    for r in store.get_store_contacts_range(cfg["sqlite_path"], month_start, month_end) + \
                store.get_puerta_daily_range(cfg["sqlite_path"], month_start, month_end):
        tienda[r["odoo_uid"]] = tienda.get(r["odoo_uid"], 0) + r["count"]
    for r in store.get_activities_daily_range(cfg["sqlite_path"], month_start, month_end):
        act[r["odoo_uid"]] = act.get(r["odoo_uid"], 0) + r["count"]

    ventas_uid, venta_total = store.get_ventas_month(cfg["sqlite_path"], day.year, day.month)

    def _diario():
        d = {}
        for src in (store.get_created_daily_range(cfg["sqlite_path"], month_start, month_end),
                    store.get_touched_daily_range(cfg["sqlite_path"], month_start, month_end),
                    store.get_store_contacts_range(cfg["sqlite_path"], month_start, month_end),
                    store.get_puerta_daily_range(cfg["sqlite_path"], month_start, month_end)):
            for r in src:
                k = (r["day"], r["odoo_uid"])
                d[k] = d.get(k, 0) + r["count"]
        return d

    diario = _diario()
    dias = [(month_start + timedelta(days=i)).isoformat() for i in range(month_end.day)]

    def _serie(uid):
        return [diario.get((dd, uid), 0) for dd in dias]

    rows = []
    for e in execs:
        funnel = {}
        for st in stages:
            if st == "Contacto Tienda":
                v = tienda.get(e["odoo_uid"], 0)
            elif st == "Seguimiento whatsapp Corporativo":
                v = act.get(e["odoo_uid"], 0)
            else:
                v = moves.get(e["odoo_uid"], {}).get(st, 0)
            funnel[st] = v or 0
        rows.append({
            "uid": e["odoo_uid"], "nombre": e["name"], "funnel": funnel,
            "venta_mes": ventas_uid.get(e["odoo_uid"], 0), "serie": _serie(e["odoo_uid"]),
        })

    global_funnel = {st: 0 for st in stages}
    for r in rows:
        for st in stages:
            global_funnel[st] += r["funnel"][st]
    serie_global = [[sum(_serie(e["odoo_uid"])[i] for e in execs) for i in range(month_end.day)]]
    return {
        "mes": f"{day.year}-{day.month:02d}",
        "dias": dias,
        "stages": stages,
        "meta_diaria": cfg.get("daily_meta", {}) or {},
        "sales_meta": cfg.get("sales_meta", 0) or 0,
        "rows": rows,
        "global": {
            "nombre": "GLOBAL", "funnel": global_funnel,
            "venta_mes": venta_total, "serie": serie_global[0],
        },
    }


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
    gestion = build_gestion(day)
    vista = build_vista(day)
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
        "gestion": gestion,
        "vista": vista,
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
    executive = request.args.get("executive")
    tyear, tmonth = month.split("-")
    path = monthly_pdf.generate_monthly_pdf(cfg, int(tyear), int(tmonth), executive)
    return send_file(path, as_attachment=True,
                     download_name=Path(path).name, mimetype="application/pdf")


@app.route("/api/pdfs", methods=["GET"])
def api_pdfs():
    month = request.args.get("month", "")
    carpeta = Path(cfg.get("pdf_output_dir", "pdf_reports"))
    pdfs = []
    if carpeta.exists():
        for p in sorted(carpeta.glob("*.pdf")):
            if month and f"-{month}.pdf" not in p.name:
                continue
            pdfs.append({
                "archivo": p.name,
                "descarga": f"/api/pdf?month={month}" if month else "",
            })
    return jsonify({"pdfs": pdfs, "mes": month})


if __name__ == "__main__":
    print("Dashboard: http://127.0.0.1:8080")
    app.run(host="127.0.0.1", port=8080, debug=False)