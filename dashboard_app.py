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

from flask import Flask, jsonify, render_template, request, send_file, Response

import store
import monthly_pdf
import graficos
import grafico_stock

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


def _bucket_labels(buckets):
    """Etiquetas de antiguedad: ['Hasta 30 días','31-60 días',...,'Más de 180 días','Sin fecha']."""
    labels = []
    for i, b in enumerate(buckets):
        if i == 0:
            labels.append(f"Hasta {b} d\u00edas")
        else:
            labels.append(f"{buckets[i - 1] + 1}-{b} d\u00edas")
    labels.append(f"M\u00e1s de {buckets[-1]} d\u00edas")
    labels.append("Sin fecha")
    return labels


def _bucket_name(age, buckets, labels):
    if age is None:
        return labels[-1]
    for i, b in enumerate(buckets):
        if age <= b:
            return labels[i]
    return labels[-2]


def _estrategias_default(labels):
    return {
        labels[0]: "Rotaci\u00f3n normal: monitorear demanda vs costo; mantener precio.",
        labels[1]: "Impulsar venta: destacar en cat\u00e1logo; mantener precio.",
        labels[2]: "Promoci\u00f3n: descuento 5-10% o combos; vigilar salida.",
        labels[3]: "Oferta activa: descuento 15-25%; evaluar devoluci\u00f3n/trueque con proveedor.",
        labels[4]: "Liquidaci\u00f3n: descuento \u2265 30%, venta a mayorista o donaci\u00f3n; revisar merma.",
        labels[5]: "Verificar la fecha de recepci\u00f3n del lote.",
    }


def _estrategias(cfg, labels):
    """Estrategia sugerida por tramo de antiguedad (configurable en stock_strategies)."""
    plan = _estrategias_default(labels)
    for k, texto in (cfg.get("stock_strategies") or {}).items():
        if k.isdigit():
            idx = int(k)
            if 0 <= idx < len(labels):
                plan[labels[idx]] = texto
        elif k in plan:
            plan[k] = texto
    return plan


def build_stock():
    """Stock disponible (solo almacenes, available>0) + antiguedad + valor segun
    compra (costo) + estrategia sugerida por tramo de tiempo."""
    filtro = [store.normalize(x) for x in (cfg.get("stock_location_filter") or [])]
    buckets = sorted((cfg.get("stock_aging_buckets") or [30, 60, 90, 180]))
    labels = _bucket_labels(buckets)
    estrategias = _estrategias(cfg, labels)
    hoy = date.today()
    rows = []
    locs = {}
    resumen = {b: {"unidades": 0, "valor": 0.0, "items": 0} for b in labels}

    def _nuevo_loc(loc_id, nombre):
        return {
            "location_id": loc_id, "location_name": nombre,
            "total_units": 0, "total_items": 0, "max_age": 0,
            "buckets": {b: 0 for b in labels},
        }

    for r in store.get_stock_cache(cfg["sqlite_path"]):
        loc_nombre = r["location_name"]
        if filtro and not any(f in store.normalize(loc_nombre) for f in filtro):
            continue
        disp = round(r["available"] or 0, 2)
        if disp <= 0:
            continue
        age = None
        if r["in_date"]:
            try:
                age = (hoy - date.fromisoformat(r["in_date"][:10])).days
            except ValueError:
                age = None
        bucket = _bucket_name(age, buckets, labels)
        costo = round(float(r["cost"] or 0), 2)
        precio = round(float(r["sale_price"] or 0), 2)
        valor = round(disp * costo, 2)
        row = {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "default_code": r["default_code"],
            "location_id": r["location_id"],
            "location_name": loc_nombre,
            "lot_name": r["lot_name"],
            "in_date": r["in_date"],
            "age_days": age,
            "bucket": bucket,
            "available": disp,
            "cost": costo,
            "price": precio,
            "value": valor,
            "strategy": estrategias[bucket],
        }
        rows.append(row)
        L = locs.setdefault(r["location_id"], _nuevo_loc(r["location_id"], loc_nombre))
        L["total_units"] += disp
        L["total_items"] += 1
        if age is not None:
            L["max_age"] = max(L["max_age"], age)
        L["buckets"][bucket] += disp
        resumen[bucket]["unidades"] += disp
        resumen[bucket]["valor"] += valor
        resumen[bucket]["items"] += 1

    rows.sort(key=lambda x: (x["age_days"] is None, -(x["age_days"] or 0)))
    locations = sorted(locs.values(), key=lambda x: store.normalize(x["location_name"]))

    for b in labels:
        resumen[b]["valor"] = round(resumen[b]["valor"], 2)

    total = {
        "total_units": round(sum(L["total_units"] for L in locations), 2),
        "total_items": sum(L["total_items"] for L in locations),
        "max_age": max((L["max_age"] for L in locations), default=0),
        "total_value": round(sum(resumen[b]["valor"] for b in labels), 2),
        "buckets": {b: round(sum(L["buckets"][b] for L in locations), 2) for b in labels},
    }
    return {
        "locations": locations,
        "bucket_labels": labels,
        "buckets": buckets,
        "rows": rows,
        "totals": total,
        "resumen": resumen,
        "estrategias": estrategias,
        "synced_at": store.stock_synced_at(cfg["sqlite_path"]),
    }


def build_daily_panel(start: date, end: date):
    """Tabla diaria por ejecutivo (acumulada en el rango)."""
    execs = _active_execs()
    touched = {}
    for r in store.get_touched_daily_range(cfg["sqlite_path"], start, end):
        touched[r["odoo_uid"]] = touched.get(r["odoo_uid"], 0) + r["count"]
    created = {}
    for r in store.get_created_daily_range(cfg["sqlite_path"], start, end):
        created[r["odoo_uid"]] = created.get(r["odoo_uid"], 0) + r["count"]
    boton = {}
    for r in store.get_store_contacts_range(cfg["sqlite_path"], start, end):
        boton[r["odoo_uid"]] = boton.get(r["odoo_uid"], 0) + r["count"]
    puerta = {}
    for r in store.get_puerta_daily_range(cfg["sqlite_path"], start, end):
        puerta[r["odoo_uid"]] = puerta.get(r["odoo_uid"], 0) + r["count"]
    actividades = {}
    for r in store.get_activities_daily_range(cfg["sqlite_path"], start, end):
        actividades[r["odoo_uid"]] = actividades.get(r["odoo_uid"], 0) + r["count"]

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


def build_funnel(start: date, end: date):
    """Embudo por flujo en el RANGO [start, end]: movimientos por etapa."""
    execs = _active_execs()

    moves = {}
    for r in store.get_stage_moves_range(cfg["sqlite_path"], start, end):
        moves[(r["odoo_uid"], r["stage"])] = moves.get((r["odoo_uid"], r["stage"]), 0) + r["count"]
    tienda = {}
    for r in store.get_store_contacts_range(cfg["sqlite_path"], start, end) + \
             store.get_puerta_daily_range(cfg["sqlite_path"], start, end):
        tienda[r["odoo_uid"]] = tienda.get(r["odoo_uid"], 0) + r["count"]
    actividades = {}
    for r in store.get_activities_daily_range(cfg["sqlite_path"], start, end):
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


def build_gestion(start: date, end: date):
    """Gestion del rango: meta (escalada) vs logrado vs pendiente por ejecutivo."""
    execs = _active_execs()
    stages = cfg.get("funnel_stages", [])
    meta_base = cfg.get("daily_meta", {}) or {st: 0 for st in stages}
    num_dias = (end - start).days + 1
    m = {st: int(meta_base.get(st, 0)) * num_dias for st in stages}
    daily = {r["uid"]: r for r in build_daily_panel(start, end)[0]}
    moves_range = {}
    for r in store.get_stage_moves_range(cfg["sqlite_path"], start, end):
        moves_range.setdefault(r["odoo_uid"], {})[r["stage"]] = r["count"]

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
                v = (moves_range.get(e["odoo_uid"], {}) or {}).get(st, 0)
            logrado[st] = v or 0
        pend = {st: max(0, m[st] - logrado[st]) for st in stages}
        ok = {st: logrado[st] >= m[st] for st in stages}
        rows.append({"nombre": e["name"], "uid": e["odoo_uid"], "meta": m,
                     "logrado": logrado, "pendiente": pend, "ok": ok})
        for st in stages:
            totals[st]["meta"] += m[st]
            totals[st]["logrado"] += logrado[st]
            totals[st]["pendiente"] += pend[st]

    ventas_uid, venta_mes = store.get_ventas_month(cfg["sqlite_path"], start.year, start.month)
    meta_venta = cfg.get("sales_meta", 0) or 0
    return {
        "stages": stages,
        "rows": rows,
        "totals": totals,
        "ventas": {"meta": meta_venta, "logrado": venta_mes,
                   "pendiente": max(0, meta_venta - venta_mes)},
    }


def build_cierre(start: date, end: date):
    """Cierre del rango por ejecutivo: prospectados, atendidos, cierres y venta."""
    execs = _active_execs()
    daily = {r["uid"]: r for r in build_daily_panel(start, end)[0]}
    moves_range = {}
    for r in store.get_stage_moves_range(cfg["sqlite_path"], start, end):
        moves_range.setdefault(r["odoo_uid"], {})[r["stage"]] = r["count"]
    venta_range = {}
    for r in store.get_ventas_daily_range(cfg["sqlite_path"], start, end):
        venta_range[r["odoo_uid"]] = venta_range.get(r["odoo_uid"], 0) + r["amount"]
    stages = cfg.get("funnel_stages", [])
    etiqueta_cierre = None
    for s in stages:
        if "cierre" in store.normalize(s):
            etiqueta_cierre = s
            break

    rows = []
    tot = {"prospect": 0, "atendidos": 0, "tienda": 0, "cierres": 0, "venta": 0.0}
    for e in execs:
        dr = daily.get(e["odoo_uid"])
        cierres = (moves_range.get(e["odoo_uid"], {}) or {}).get(etiqueta_cierre, 0) if etiqueta_cierre else 0
        venta = venta_range.get(e["odoo_uid"], 0) or 0
        row = {
            "nombre": e["name"],
            "uid": e["odoo_uid"],
            "prospect": (dr["creados"] if dr else 0),
            "atendidos": (dr["atendidos"] if dr else 0),
            "tienda": (dr["tienda"] if dr else 0),
            "cierres": cierres or 0,
            "venta": venta,
        }
        rows.append(row)
        tot["prospect"] += row["prospect"]
        tot["atendidos"] += row["atendidos"]
        tot["tienda"] += row["tienda"]
        tot["cierres"] += row["cierres"]
        tot["venta"] += venta
    return {"rows": rows, "total": tot}


def build_historico():
    """Historico por dia: matriz dias x ejecutivo con gestion diaria (prospect,
    atendidos, tienda, cierres, venta). Reusa build_cierre por dia (cache local)."""
    execs = _active_execs()
    dias = store.get_dias_disponibles(cfg["sqlite_path"])
    exec_uid = [{"uid": e["odoo_uid"], "nombre": e["name"]} for e in execs]
    rend = {}
    totales = {}
    for ds in dias:
        d = date.fromisoformat(ds)
        c = build_cierre(d, d)
        por_uid = {r["uid"]: r for r in c["rows"]}
        rend[ds] = {str(e["uid"]): por_uid.get(e["uid"], {
            "nombre": e["nombre"], "prospect": 0, "atendidos": 0,
            "tienda": 0, "cierres": 0, "venta": 0.0}) for e in exec_uid}
        totales[ds] = c["total"]
    return {"dias": dias, "ejecutivos": exec_uid, "rend": rend, "totales": totales}


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
    return render_template(
        "index.html",
        refresh_min=cfg.get("refresh_min", 60),
        hora_envio=cfg.get("hora_envio_gestion", "20:00"),
        tiene_ghl=bool(cfg.get("gohighlevel", {}).get("api_key")),
    )


@app.route("/stock")
def stock_page():
    return render_template(
        "stock.html",
        refresh_min=cfg.get("refresh_min", 60),
    )


@app.route("/api/stock", methods=["GET"])
def api_stock():
    return jsonify({**build_stock(), "last_sync": store.last_sync_ok(cfg["sqlite_path"])})


@app.route("/api/grafico_stock")
def api_grafico_stock():
    png = grafico_stock.grafico_stock(build_stock())
    if not png:
        return jsonify({"ok": False, "error": "Sin stock con fecha"}), 404
    return Response(png, mimetype="image/png")


@app.route("/api/data", methods=["GET"])
def api_data():
    desde = request.args.get("from")
    hasta = request.args.get("to")
    try:
        day_desde = date.fromisoformat(desde) if desde else date.today()
    except ValueError:
        day_desde = date.today()
    try:
        day_hasta = date.fromisoformat(hasta) if hasta else date.today()
    except ValueError:
        day_hasta = date.today()
    if day_desde > day_hasta:
        day_desde = day_hasta
    day = day_hasta  # dia de referencia para embudo y vista
    daily, daily_total = build_daily_panel(day_desde, day_hasta)
    header, funnel_rows, funnel_total = build_funnel(day_desde, day_hasta)
    gestion = build_gestion(day_desde, day_hasta)
    vista = build_vista(day)
    cierre = build_cierre(day_desde, day_hasta)
    historico = build_historico()
    if not store.last_snapshot_date(cfg["sqlite_path"]):
        funnel_rows = []
    last_sync = store.last_sync_ok(cfg["sqlite_path"])
    return jsonify({
        "dia_desde": day_desde.isoformat(),
        "dia_hasta": day_hasta.isoformat(),
        "daily": daily,
        "daily_total": daily_total,
        "funnel_header": header,
        "funnel_rows": funnel_rows,
        "funnel_total": funnel_total,
        "gestion": gestion,
        "vista": vista,
        "cierre": cierre,
        "historico": historico,
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


@app.route("/api/grafico")
def api_grafico():
    nombre = request.args.get("ejecutivo", "GLOBAL")
    desde = request.args.get("desde") or None
    hasta = request.args.get("hasta") or None
    hist = build_historico()
    series = [h["nombre"] for h in hist["ejecutivos"]]
    if nombre not in series:
        nombre = "GLOBAL"
    for arg in (desde, hasta):
        if arg:
            try:
                date.fromisoformat(arg)
            except ValueError:
                desde = hasta = None
                break
    png = graficos.grafico_historico(hist, nombre, desde, hasta)
    return Response(png, mimetype="image/png")


@app.route("/api/gestion_enviar", methods=["POST"])
def api_gestion_enviar():
    body = request.get_json(silent=True) or {}
    d = date.fromisoformat(body["day"]) if body.get("day") else date.today()
    if not cfg.get("gohighlevel", {}).get("api_key"):
        return jsonify({"ok": False,
                        "error": "GoHighLevel NO configurado: rellena gohighlevel.api_key en config.json"}), 400
    try:
        import gohighlevel
        resumen, por_ejec = gohighlevel.build_mensajes(d)
        enviados = 0
        for tel in cfg.get("gerencia_whatsapp", []):
            if tel:
                gohighlevel.enviar_whatsapp(resumen, tel)
                enviados += 1
        for nombre_norm, tel in cfg.get("ejecutivos_whatsapp", {}).items():
            if tel and nombre_norm in por_ejec:
                gohighlevel.enviar_whatsapp(por_ejec[nombre_norm], tel)
                enviados += 1
        return jsonify({"ok": True, "day": d.isoformat(), "enviados": enviados})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


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