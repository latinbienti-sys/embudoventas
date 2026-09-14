# -*- coding: utf-8 -*-
"""Tarea diaria: baja SOLO LECTURA desde Odoo al cache SQLite.

Uso:
    python sync_to_local.py                          # sincroniza solo el dia de hoy
    python sync_to_local.py --backfill 45            # primer uso: ultimos 45 dias
    python sync_to_local.py --until 2026-08-31       # sincroniza hasta una fecha
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import store
from odoo_client import OdooClient


def load_config():
    cfg_path = Path(__file__).parent / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg["odoo"]["url"] or cfg["odoo"]["api_key"] in (None, "", "TU_API_KEY"):
        raise SystemExit(
            "config.json sin datos. Copia config.example.json a config.json y completa los datos de conexion."
        )
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=0, help="dias hacia atras a sincronizar")
    ap.add_argument("--until", default=None, help="fecha maxima AAA-MM-DD (default: hoy)")
    args = ap.parse_args()

    cfg = load_config()
    tz = ZoneInfo(cfg.get("timezone", "America/Caracas"))
    store.init_db(cfg["sqlite_path"])

    client = OdooClient(
        cfg["odoo"]["url"], cfg["odoo"]["db"], cfg["odoo"]["user"], cfg["odoo"]["api_key"]
    ).connect()

    print("Conectado a", cfg["odoo"]["url"], "uid", client.uid)

    # ---------- Ejecutivos ----------
    execs = client.get_executives()
    # union con los ejecutivos configurados manualmente (por nombre)
    extra_names = [n for n in cfg.get("executives", [])]
    known = {e["name"].lower(): e for e in execs}
    for name in extra_names:
        if name not in known:
            execs.append({"id": 0, "name": name})
    store.upsert_executives(cfg["sqlite_path"], execs)
    store.mark_executives_inactive(cfg["sqlite_path"], [e["id"] for e in execs if e["id"]])
    print(f"Ejecutivos detectados: {len(execs)}")

    # ---------- Etapas ----------
    stage_map = client.get_stages()
    stage_names = cfg.get("funnel_stages", [])
    print("Etapas CRM:", len(stage_map), "| Etapas del embudo configuradas:", len(stage_names))

    # ---------- Rango de dias a procesar ----------
    until = date.fromisoformat(args.until) if args.until else date.today()
    since = until - timedelta(days=args.backfill) if args.backfill else until
    print(f"Procesando del {since} al {until}")

    # ---------- Snapshot del embudo (estado actual por dia procesado) ----------
    # El snapshot refleja el pipeline tal como estaba en la fecha del rango.
    # Para backfill completo se produce un solo snapshot por dia reprocesando leads.
    all_leads = client.get_leads(["id", "user_id", "stage_id", "create_date", "write_date"])
    print("Leads activos:", len(all_leads))

    for d in range((until - since).days + 1):
        day = since + timedelta(days=d)
        created = client.get_lead_created_in_range(
            day, day + timedelta(days=1), ["id", "user_id", "create_date", "write_date"]
        )
        touched = client.get_lead_touched_in_range(
            day, day + timedelta(days=1), ["id", "user_id", "create_date", "write_date"]
        )

        funnel = OdooClient.funnel_from_leads(all_leads, stage_map, stage_names, tz)
        store.upsert_funnel_snapshot(cfg["sqlite_path"], day, funnel)

        by_day_c = OdooClient.created_by_day(created, tz)
        by_day_t = OdooClient.touched_by_day(touched, tz)
        store.upsert_created_daily(cfg["sqlite_path"], by_day_c, tz)
        store.upsert_touched_daily(cfg["sqlite_path"], by_day_t, tz)
        print(f"  {day}: funnel ok | creados {sum(v for u in by_day_c.values() for v in u.values())} | atendidos {sum(v for u in by_day_t.values() for v in u.values())}")

    store.log_sync(cfg["sqlite_path"], True, f"sincronizado {since} -> {until}")
    print("Listo. Datos guardados en", cfg["sqlite_path"])


if __name__ == "__main__":
    main()