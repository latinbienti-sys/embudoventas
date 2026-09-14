# -*- coding: utf-8 -*-
"""Genera el PDF mensual visual del embudo de ventas (desde cache local).

Uso:
    python monthly_pdf.py --month 2026-08
    python monthly_pdf.py --month 2026-08 --executive "LADY DIANA TORO"
"""
import argparse
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

import store

BASE = Path(__file__).parent

MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
         7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}


def load_config():
    with open(BASE / "config.json", encoding="utf-8") as f:
        return json.load(f)


def _barra(ax, valores, etiquetas, titulo, color="#0f3b6e", total=None):
    ax.bar(range(len(etiquetas)), valores, color=color, width=0.55)
    ax.set_xticks(range(len(etiquetas)))
    ax.set_xticklabels(etiquetas, rotation=25, ha="right", fontsize=8)
    for i, v in enumerate(valores):
        if v:
            ax.text(i, v, str(int(v)), ha="center", va="bottom", fontsize=9)
    ax.set_title(titulo, fontsize=12, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def generate_monthly_pdf(cfg, year, month, executive=None, out_path=None):
    db = cfg["sqlite_path"]
    stages = cfg.get("funnel_stages", [])
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    execs = store.get_executives(db)
    exclude = {store.normalize(e) for e in cfg.get("executives_exclude", [])}
    execs = [e for e in execs if store.normalize(e["name"]) not in exclude]
    active = [store.normalize(e) for e in cfg.get("executives_active", [])]
    if active:
        execs = [e for e in execs
                 if any(t in store.normalize(e["name"]) or store.normalize(e["name"]) in t
                        for t in active)]
    if executive:
        execs = [e for e in execs if executive.lower() in e["name"].lower()]
    if not execs:
        raise SystemExit("Sin ejecutivos. Ejecuta antes sync_to_local.py")

    funnel_rows = store.get_funnel_month(db, year, month)
    funnel = {(r["odoo_uid"], r["stage"]): r["count"] for r in funnel_rows}
    tienda_rows = store.get_store_contacts_range(db, month_start, month_end)
    tienda_sum = {}
    for r in tienda_rows:
        tienda_sum[r["odoo_uid"]] = tienda_sum.get(r["odoo_uid"], 0) + r["count"]
    puerta_rows = store.get_puerta_daily_range(db, month_start, month_end)
    for r in puerta_rows:
        tienda_sum[r["odoo_uid"]] = tienda_sum.get(r["odoo_uid"], 0) + r["count"]
    act_rows = store.get_activities_daily_range(db, month_start, month_end)
    act_sum = {}
    for r in act_rows:
        act_sum[r["odoo_uid"]] = act_sum.get(r["odoo_uid"], 0) + r["count"]
    move_rows = store.get_stage_moves_month(db, year, month)
    moves = {(r["odoo_uid"], r["stage"]): r["count"] for r in move_rows}

    created = store.get_created_daily_range(db, month_start, month_end)
    touched = store.get_touched_daily_range(db, month_start, month_end)
    created_by = {(r["day"], r["odoo_uid"]): r["count"] for r in created}
    touched_by = {(r["day"], r["odoo_uid"]): r["count"] for r in touched}
    tienda_by = {(r["day"], r["odoo_uid"]): r["count"] for r in tienda_rows}
    for r in puerta_rows:
        tienda_by[(r["day"], r["odoo_uid"])] = tienda_by.get((r["day"], r["odoo_uid"]), 0) + r["count"]

    db_path = cfg.get("pdf_output_dir", "pdf_reports")
    Path(db_path).mkdir(exist_ok=True)
    nombre = executive.replace(" ", "_").upper() if executive else "GLOBAL"
    path = (out_path or Path(db_path)) / f"EMBUDO_VENTAS_{nombre}_{year}-{month:02d}.pdf"

    with PdfPages(path) as pdf:
        # ---------------- Pagina 1: resumen embudo ------------------ #
        fig, axs = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [1.5, 1]})
        fig.suptitle(f"TABLERO DE GESTION DE VENTAS - {MESES[month].upper()} {year}\n"
                     f"EMBUDO DE VENTAS - {'GLOBAL' if not executive else executive.upper()}",
                     fontsize=14, fontweight="bold")

        cabecera = ["Ejecutivo"] + stages
        matriz = []
        for e in execs:
            fila = [e["name"]]
            for st in stages:
                if st == "Contacto Tienda":
                    v = tienda_sum.get(e["odoo_uid"], 0)
                elif st == "Seguimiento whatsapp Corporativo":
                    v = act_sum.get(e["odoo_uid"], 0)
                else:
                    v = moves.get((e["odoo_uid"], st), 0)
                fila.append(v)
            matriz.append(fila)
        totales = ["TOTAL"] + [sum(f[i] for f in matriz) for i in range(1, len(stages) + 1)]

        ax = axs[0]
        ax.axis("off")
        tbl = ax.table(cellText=matriz + [totales], colLabels=cabecera, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1, 1.4)
        for j in range(len(cabecera)):
            celda = tbl[0, j]
            celda.set_facecolor("#0f3b6e")
            celda.set_text_props(color="white", fontweight="bold")
        fila_total = len(matriz)
        for j in range(len(cabecera)):
            tbl[fila_total, j].set_facecolor("#eef1f5")

        ax = axs[1]
        vals = [sum(f[i] for f in matriz) for i in range(1, len(stages) + 1)]
        _barra(ax, vals, stages, "Volumen total por etapa", color="#e07b2a")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ---------------- Pagina 2: atendidos diarios ------------- #
        fig, ax = plt.subplots(figsize=(11, 7))
        fig.suptitle(f"Clientes atendidos por ejecutivo - {MESES[month].capitalize()} {year}",
                     fontsize=13, fontweight="bold")
        dias = [(month_start + timedelta(days=d)).isoformat() for d in range(last_day)]
        for e in execs:
            serie = []
            for d in dias:
                creados = created_by.get((d, e["odoo_uid"]), 0)
                atendidos = touched_by.get((d, e["odoo_uid"]), 0)
                tienda = tienda_by.get((d, e["odoo_uid"]), 0)
                serie.append(creados + atendidos + tienda)
            ax.plot(range(1, last_day + 1), serie, marker="o", markersize=3,
                    label=e["name"], linewidth=1.4)
        ax.set_xlabel("Dia del mes")
        ax.set_ylabel("Clientes atendidos (CRM + tienda)")
        ax.set_xticks(range(1, last_day + 1, max(1, last_day // 16)))
        ax.legend(fontsize=8, ncol=3)
        ax.grid(alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    print("PDF generado:", path)
    return str(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="AAA-MM ejemplo 2026-08")
    ap.add_argument("--executive", default=None, help="nombre del ejecutivo (opcional)")
    args = ap.parse_args()
    cfg = load_config()
    y, m = (int(x) for x in args.month.split("-"))
    generate_monthly_pdf(cfg, y, m, args.executive)