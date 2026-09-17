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

            CREATE TABLE IF NOT EXISTS puerta_daily (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS ventas_daily (
                day         TEXT NOT NULL,
                odoo_uid    INTEGER NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (day, odoo_uid)
            );

            CREATE TABLE IF NOT EXISTS lc_credimotos (
                partner_id   INTEGER PRIMARY KEY,
                name         TEXT NOT NULL,
                asesor_uid   INTEGER,
                asesor_name  TEXT,
                lead_id      INTEGER,
                lead_stage   TEXT,
                funnel_stage TEXT,
                updated_at   TEXT
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


def upsert_puerta_daily(path, by_day, tz):
    """by_day: {dia: {uid: n}} actividades 'Atencion Puerta' (Contacto Tienda)."""
    with closing(get_conn(path)) as c:
        for day, counts in by_day.items():
            c.execute("DELETE FROM puerta_daily WHERE day=?", (day.isoformat(),))
            for uid, cnt in counts.items():
                c.execute(
                    "INSERT OR REPLACE INTO puerta_daily (day, odoo_uid, count) VALUES (?,?,?)",
                    (day.isoformat(), int(uid or 0), int(cnt)),
                )
        c.commit()


def upsert_ventas_daily(path, by_day_amounts, tz):
    """by_day_amounts: {dia: {uid: monto}} ventas del mes (leads en Cierre)."""
    with closing(get_conn(path)) as c:
        for day, amounts in by_day_amounts.items():
            c.execute("DELETE FROM ventas_daily WHERE day=?", (day.isoformat(),))
            for uid, monto in amounts.items():
                c.execute(
                    "INSERT OR REPLACE INTO ventas_daily (day, odoo_uid, amount) VALUES (?,?,?)",
                    (day.isoformat(), int(uid or 0), float(monto)),
                )
        c.commit()


def upsert_lc_credimotos(path, rows):
    """Snapshot completo de contactos CREDIMOTOS (modulo contactos)."""
    with closing(get_conn(path)) as c:
        c.execute("DELETE FROM lc_credimotos")
        for r in rows:
            c.execute(
                """INSERT OR REPLACE INTO lc_credimotos
                   (partner_id, name, asesor_uid, asesor_name, lead_id, lead_stage,
                    funnel_stage, updated_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))""",
                (int(r["partner_id"]), r["name"], r.get("asesor_uid") or None,
                 r.get("asesor_name") or "", r.get("lead_id"), r.get("lead_stage") or "",
                 r.get("funnel_stage") or ""),
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


def get_puerta_daily_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, count FROM puerta_daily WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_ventas_month(path, year, month):
    """Ventas del mes (monto de leads en Cierre): {uid: monto} y total."""
    with closing(get_conn(path)) as c:
        rows = [dict(r) for r in c.execute(
            "SELECT odoo_uid, SUM(amount) AS amount FROM ventas_daily "
            "WHERE day BETWEEN ? AND ? GROUP BY odoo_uid",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"),
        )]
        por_uid = {r["odoo_uid"]: r["amount"] for r in rows}
        return por_uid, sum(por_uid.values())


def get_ventas_daily_range(path, start, end):
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT day, odoo_uid, amount FROM ventas_daily WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )]


def get_lc_credimotos(path):
    """Contactos CREDIMOTOS (snapshot actual del modulo contactos)."""
    with closing(get_conn(path)) as c:
        return [dict(r) for r in c.execute(
            "SELECT partner_id, name, asesor_uid, asesor_name, lead_id, "
            "lead_stage, funnel_stage FROM lc_credimotos ORDER BY name"
        )]


def last_snapshot_date(path):
    with closing(get_conn(path)) as c:
        row = c.execute("SELECT MAX(snap_date) AS md FROM funnel_snapshot").fetchone()
        return row["md"] if row and row["md"] else None


def last_sync_ok(path):
    with closing(get_conn(path)) as c:
        row = c.execute("SELECT run_at, ok FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def get_dias_disponibles(path):
    """Dias con datos en el cache (union de las tablas diarias), ordenados."""
    with closing(get_conn(path)) as c:
        rows = c.execute(
            "SELECT day FROM created_daily UNION SELECT day FROM touched_daily "
            "UNION SELECT day FROM activities_daily UNION SELECT day FROM stage_moves "
            "UNION SELECT day FROM puerta_daily UNION SELECT day FROM ventas_daily "
            "ORDER BY day"
        ).fetchall()
        return [r["day"] for r in rows]