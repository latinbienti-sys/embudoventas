# -*- coding: utf-8 -*-
"""Cliente XML-RPC de Odoo 16 (SOLO LECTURA).

Garantías:
- Solo se ejecutan metodos de lectura (authenticate, search_read, read, search).
- NUNCA se ejecutan create/write/unlink sobre Odoo: el ERP no se modifica.
- Se usa unicamente para bajar datos al cache local.
"""
import xmlrpc.client
from collections import defaultdict
from datetime import datetime, date


class OdooClient:
    def __init__(self, url, db, user, api_key):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.api_key = api_key
        self.common = xmlrpc.client.ServerProxy(
            "{}://{}/xmlrpc/2/common".format("https" if self.url.startswith("https") else "http",
                                             self.url.replace("https://", "").replace("http://", ""))
        )

    def connect(self):
        self.uid = self.common.authenticate(self.db, self.user, self.api_key, {})
        if not self.uid:
            raise ConnectionError("Autenticacion fallida en Odoo. Revisa url, db, usuario y api key.")
        self.models = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/object")
        return self

    # ------------------------------------------------------------------ #
    def _exec(self, model, method, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, model, method, args, kwargs
        )

    def search(self, model, domain, limit=0):
        kwargs = {"limit": limit} if limit else {}
        return self._exec(model, "search", [domain], kwargs)

    def search_read(self, model, domain, fields, limit=0, order=""):
        kwargs = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self._exec(model, "search_read", [domain], kwargs)

    def read(self, model, ids, fields=None):
        kwargs = {"fields": fields} if fields else {}
        return self._exec(model, "read", [ids], kwargs)

    # ------------------------------------------------------------------ #
    def get_stages(self):
        """Devuelve mapeo {id: nombre} de todas las etapas de crm.stage."""
        rows = self.search_read("crm.stage", [], ["id", "name"], order="sequence")
        return {r["id"]: r["name"] for r in rows}

    def get_leads(self, fields):
        """Todos los leads activos no perdidos (solo lectura)."""
        domain = [("active", "=", True)]
        try:
            domain = [("active", "=", True), ("is_lost", "=", False)]
        except Exception:
            pass
        return self.search_read("crm.lead", domain, fields)

    def get_lead_created_in_range(self, since, until, fields):
        """Leads creados en [since, until) (solo lectura)."""
        since_str = since.strftime("%Y-%m-%d 00:00:00")
        until_str = until.strftime("%Y-%m-%d 00:00:00")
        domain = [("create_date", ">=", since_str)]
        if until:
            domain.append(("create_date", "<", until_str))
        return self.search_read("crm.lead", domain, fields)

    def get_lead_touched_in_range(self, since, until, fields):
        """Leads actualizados (atendidos) en [since, until) (solo lectura)."""
        since_str = since.strftime("%Y-%m-%d 00:00:00")
        domain = [("write_date", ">=", since_str)]
        if until:
            domain.append(("write_date", "<", until.strftime("%Y-%m-%d 00:00:00")))
        return self.search_read("crm.lead", domain, fields)

    def get_executives(self):
        """Usuarios internos que aparecen en leads del CRM (ejecutivos)."""
        rows = self.search_read("res.users", [("active", "=", True), ("share", "=", False)],
                                ["id", "name", "team_id"])
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    # ------------------------------------------------------------------ #
    # Agregados utiles
    # ------------------------------------------------------------------ #
    @staticmethod
    def funnel_from_leads(leads, stage_map, stage_names, tz):
        """Crea snapshot {stage_nombre: {ejecutivo_id: n}} para los stages configurados."""
        funnel = {name: defaultdict(int) for name in stage_names}
        for lead in leads:
            stage_id = lead.get("stage_id")[0] if lead.get("stage_id") else None
            name = stage_map.get(stage_id) if stage_id else None
            if not name:
                continue
            user_id = lead.get("user_id")[0] if lead.get("user_id") else None
            if name not in funnel:
                funnel[name] = defaultdict(int)
            funnel[name][user_id or 0] += 1
        return funnel

    @staticmethod
    def created_by_day(leads, tz):
        """{fecha: {user_id: n}} cantidad de leads creados por dia por ejecutivo."""
        out = defaultdict(lambda: defaultdict(int))
        for lead in leads:
            create_date = lead.get("create_date")
            if not create_date:
                continue
            dt = datetime.fromisoformat(create_date).astimezone(tz).date()
            user_id = lead.get("user_id")[0] if lead.get("user_id") else 0
            out[dt][user_id] += 1
        return out

    @staticmethod
    def touched_by_day(leads, tz):
        """{fecha: {user_id: n}} cantidad de leads atendidos (write_date) por dia."""
        out = defaultdict(lambda: defaultdict(int))
        for lead in leads:
            write_date = lead.get("write_date")
            if not write_date:
                continue
            dt = datetime.fromisoformat(write_date).astimezone(tz).date()
            user_id = lead.get("user_id")[0] if lead.get("user_id") else 0
            out[dt][user_id] += 1
        return out