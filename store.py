# -*- coding: utf-8 -*-
"""Capa SQLite local. NO toca Odoo."""

import sqlite3
import unicodedata
from contextlib import closing
from datetime import date


def normalize(texto):
    """Minusculas y sin acentos, para comparar nombres (Asesoria = Asesoría)."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


def get_conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    with closing(get_conn(path)) as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS executives (
                odoo_uid  INTEGER PRIMARY KEY,
                name      TEXT NOT NULL,
                active    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS funnel_snapshot (
                snap_date   TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                stage       TEXT NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (snap_date, odoo_uid, stage)
            );

            CREATE TABLE IF NOT EXISTS created_daily (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS touched_daily (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS activities_daily (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS stage_moves (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                stage       TEXT NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid, stage)
            );

            CREATE TABLE IF NOT EXISTS store_contacts (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      TEXT NOT NULL,
                ok          INTEGER NOT NULL,
                detail      TEXT
            );
            """
        )
        c.commit()


# --------------------------------------------------------------------------- #
# Upserts / inserciones
# --------------------------------------------------------------------------- #
def upsert_executives(path, rows):
    with closing(get_conn(path)) as c:
        for r in rows:
            c.execute(
                "INSERT OR REPLACE INTO executives (odoo_uid, name, active) VALUES (?,?,1)",
                (r["id"], r["name"]),
            )
        c.commit()


def mark_executives_inactive(path, active_ids):
    ids = [int(i) for i in active_ids]
    with closing(get_conn(path)) as c:
        if ids:
            qmarks = ",".join("?" * len(ids))
            c.execute(f"UPDATE executives SET active=0 WHERE odoo_uid NOT IN ({qmarks})", ids)
        c.commit()


def upsert_funnel_snapshot(path, snap_date: date, funnel_by_stage):
    """funnel_by_stage: {stage: {uid: count}}"""
    with closing(get_conn(path)) as c:
        for stage, counts in funnel_by_stage.items():
            for uid, cnt in counts.items():
                c.execute(
                    """INSERT OR REPLACE INTO funnel_snapshot (snap_date, odoo_uid, stage, count, created_at)
                       VALUES (?,?,?,?,datetime('now','localtime'))""",
                    (snap_date.isoformat(), int(uid or 0), stage, int(cnt)),
                )
        c.commit()


def upsert_created_daily(path, by_day, tz):
    with closing(get_conn(path)) as c:
        for day, counts in by_day.items():
            c.execute("DELETE FROM created_daily WHERE day=?", (day.isoformat(),))
            for uid, cnt in counts.items():
                c.execute(
                    "INSERT OR REPLACE INTO created_daily (day, odoo_uid, count) VALUES (?,?,?)",
                    (day.isoformat(), int(uid or 0), int(cnt)),
                )
        c.commit()


def upsert_touched_daily(path, by_day, tz):
    with closing(get_conn(path)) as c:
        for day, counts in by_day.items():
            c.execute("DELETE FROM touched_daily WHERE day=?", (day.isoformat(),))
            for uid, cnt in counts.items():
                c.execute(
                    "INSERT OR REPLACE INTO touched_daily (day, odoo_uid, count) VALUES (?,?,?)",
                    (day.isoformat(), int(uid or 0), int(cnt)),
                )
        c.commit()


def upsert_activities_daily(path, by_day, tz):
    with closing(get_conn(path)) as c:
        for day, counts in by_day.items():
            c.execute("DELETE FROM activities_daily WHERE day=?", (day.isoformat(),))
            for uid, cnt in counts.items():
                c.execute(
                    "INSERT OR REPLACE INTO activities_daily (day, odoo_uid, count) VALUES (?,?,?)",
                    (day.isoformat(), int(uid or 0), int(cnt)),
                )
        c.commit()


def upsert_stage_moves(path, by_day, tz):
    """by_day: {dia: {uid: {etapa_embudo: n}}} movimientos de etapa."""
    with closing(get_conn(path)) as c:
        for day, users in by_day.items():
            c.execute("DELETE FROM stage_moves WHERE day=?", (day.isoformat(),))
            for uid, stages in users.items():
                for stage, cnt in stages.items():
                    c.execute(
                        "INSERT OR REPLACE INTO stage_moves (day, odoo_uid, stage, count) VALUES (?,?,?,?)",
                        (day.isoformat(), int(uid or 0), stage, int(cnt)),
                    )
        c.commit()


def increment_store_contact(path, day, odoo_uid, delta=1):
    """Botón del tablero: suma/resta contacto tienda en cache local."""
    with closing(get_conn(path)) as c:
        c.execute(
            """INSERT INTO store_contacts (day, odoo_uid, count, updated_at)
               VALUES (?,?,?,datetime('now','localtime'))
               ON CONFLICT(day, odoo_uid)
               DO UPDATE SET count = count + ?, updated_at = datetime('now','localtime')""",
            (day, int(odoo_uid), int(delta), int(delta)),
        )
        c.commit()
        row = c.execute(
            "SELECT count FROM store_contacts WHERE day=? AND odoo_uid=?",
            (day, int(odoo_uid)),
        ).fetchone()
        return row["count"] if row else 0


def log_sync(path, ok, detail=""):
    with closing(get_conn(path)) as c:
        c.execute(
            "INSERT INTO sync_log (run_at, ok, detail) VALUES (datetime('now','localtime'),?,?)",
            (1 if ok else 0, detail[:500]),
        )
        c.commit()


# --------------------------------------------------------------------------- #
# Consultas para tablero y PDF
# --------------------------------------------------------------------------- #
def get_executives(path, include_inactive=False):
    with closing(get_conn(path)) as c:
        sql = "SELECT odoo_uid, name, active FROM executives"
        if not include_inactive:
            sql += " WHERE active=1"
        return [dict(r) for r in c.execute(sql + " ORDER BY name")]


def get_funnel_snapshot(path, day):
    """Snapshot del embudo de un dia concreto. Lista de dicts por (stage, uid)."""
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT snap_date, odoo_uid, stage, count FROM funnel_snapshot WHERE snap_date=?",
            (day.isoformat(),),
        )]


def get_funnel_month(path, year, month):
    """Ultimo snapshot de cada (uid, stage) dentro del mes."""
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            """SELECT f.odoo_uid, f.stage, f.count, f.snap_date
               FROM funnel_snapshot f
               INNER JOIN (SELECT odoo_uid, stage, MAX(snap_date) AS md
                           FROM funnel_snapshot
                           WHERE snap_date BETWEEN ? AND ?
                           GROUP BY odoo_uid, stage) m
               ON f.odoo_uid=m.odoo_uid AND f.stage=m.stage AND f.snap_date=m.md""",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"),
        )]


def get_touched_daily_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, count FROM touched_daily WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_activities_daily_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, count FROM activities_daily WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_stage_moves_month(path, year, month):
    """Movimientos de etapa (flujo) del mes, sumados por (ejecutivo, etapa)."""
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT odoo_uid, stage, SUM(count) AS count FROM stage_moves "
            "WHERE day BETWEEN ? AND ? GROUP BY odoo_uid, stage",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"),
        )]


def get_stage_moves_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, stage, count FROM stage_moves WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_created_daily_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, count FROM created_daily WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_store_contacts_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, count FROM store_contacts WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def last_snapshot_date(path):
    with closing(get_conn(path)) as c:
        row = c.execute("SELECT MAX(snap_date) AS md FROM funnel_snapshot").fetchone()
        return row["md"] if row and row["md"] else None


def last_sync_ok(path):
    with closing(get_conn(path)) as c:
        row = c.execute("SELECT run_at, ok FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None