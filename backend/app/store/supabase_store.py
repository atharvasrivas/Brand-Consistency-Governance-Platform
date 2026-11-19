"""Supabase (PostgREST) store over one table, bg_docs. Uses the service key, which stays on the server.

Covered by tests with a fake HTTP layer; verified against a live project only for reads/writes reported in the README.
Apply schema/supabase.sql first.
"""
import requests

from .base import Store


class SupabaseStore(Store):
    def __init__(self, url, key, session=None, timeout=10):
        self.base = f"{url.rstrip('/')}/rest/v1/bg_docs"
        self.s = session or requests.Session()
        self.h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.timeout = timeout

    def _req(self, method, params=None, json=None, prefer=None):
        h = dict(self.h)
        if prefer:
            h["Prefer"] = prefer
        r = self.s.request(method, self.base, params=params, json=json, headers=h, timeout=self.timeout)
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase {method} bg_docs failed: {r.status_code} {r.text[:200]}")
        return r.json() if r.text else None

    def list(self, kind):
        rows = self._req("GET", {"select": "data", "kind": f"eq.{kind}", "order": "created_at.asc"})
        return [r["data"] for r in rows]

    def get(self, kind, id):
        rows = self._req("GET", {"select": "data", "kind": f"eq.{kind}", "id": f"eq.{id}", "limit": "1"})
        return rows[0]["data"] if rows else None

    def put(self, kind, id, data):
        self._req("POST", {"on_conflict": "kind,id"}, json={"kind": kind, "id": id, "data": data},
                  prefer="resolution=merge-duplicates")

    def delete(self, kind, id):
        self._req("DELETE", {"kind": f"eq.{kind}", "id": f"eq.{id}"})
