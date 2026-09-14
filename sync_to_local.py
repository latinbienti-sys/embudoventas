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
    # Indice por nombre normalizado para atribuir los movimientos (el autor es
    # un res.partner, no un res.users).
    name2uid = {store.normalize(e["name"]): e["id"] for e in execs if e["id"]}
    print(f"Ejecutivos detectados: {len(execs)}")

    # ---------- Etapas ----------
    stage_map = client.get_stages()
    stage_names = cfg.get("funnel_stages", [])
    stage_mapping = cfg.get("stage_mapping", {}) or {s: [s] for s in stage_names}
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
        activities = client.get_activities_in_range(day, day + timedelta(days=1))
        moves, tracking, authors = client.get_stage_moves_in_range(day, day + timedelta(days=1))

        funnel, unmapped = OdooClient.funnel_from_leads(
            all_leads, stage_map, stage_names, stage_mapping, tz)
        store.upsert_funnel_snapshot(cfg["sqlite_path"], day, funnel)
        if unmapped and d == 0:
            print("  AVISO: etapas CRM sin mapear en embudo:", sorted(unmapped))

        by_day_c = OdooClient.created_by_day(created, tz)
        by_day_t = OdooClient.touched_by_day(touched, tz)
        by_day_a = OdooClient.activities_by_day(activities, tz)
        by_day_m = OdooClient.moves_by_day(moves, tracking, stage_mapping, stage_names, tz, authors)
        # Reagrupa movimientos por UID del ejecutivo (via nombre del autor).
        by_day_m_uid = {}
        for day, users in by_day_m.items():
            for auto_nombre, stages in users.items():
                uid = name2uid.get(auto_nombre)
                if not uid:
                    continue  # autor sin ejecutivo activo: se omite
                by_day_m_uid.setdefault(day, {})[uid] = {
                    s: by_day_m_uid.get(day, {}).get(uid, {}).get(s, 0) + cnt
                    for s, cnt in stages.items()
                }
        store.upsert_created_daily(cfg["sqlite_path"], by_day_c, tz)
        store.upsert_touched_daily(cfg["sqlite_path"], by_day_t, tz)
        store.upsert_activities_daily(cfg["sqlite_path"], by_day_a, tz)
        store.upsert_stage_moves(cfg["sqlite_path"], by_day_m_uid, tz)
        total_a = sum(v for u in by_day_a.values() for v in u.values())
        total_c = sum(v for u in by_day_c.values() for v in u.values())
        total_t = sum(v for u in by_day_t.values() for v in u.values())
        total_m = sum(c for u in by_day_m_uid.values() for s in u.values() for c in s.values())
        print(f"  {day}: funnel ok | creados {total_c} | atendidos {total_t} | actividades {total_a} | movimientos {total_m}")

    store.log_sync(cfg["sqlite_path"], True, f"sincronizado {since} -> {until}")
    print("Listo. Datos guardados en", cfg["sqlite_path"])


if __name__ == "__main__":
    main()