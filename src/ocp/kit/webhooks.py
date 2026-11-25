"""Receiving alert webhooks into case management. Each event is signed (HMAC-SHA256 over timestamp and body),
checked against a time window, applied once (an event id is recorded in the same transaction as its effect), and
applied in order (an older version of an alert never overwrites a newer one). The first event for an alert opens its
case and one ticket in the case system, whichever event arrives first; later events update it, and each applied
event is written to the case's activity log.

Safeguards can be switched off one at a time for the lab: signature, dedupe, versioning."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any

TOLERANCE_S = 300


def sign(secret: str, ts: int, body: str) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, header: str, body: str, now: int, tolerance: int = TOLERANCE_S) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        mac = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(now - ts) > tolerance:
        return False
    good = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, mac)


@dataclass
class Safeguards:
    signature: bool = True
    dedupe: bool = True
    versioning: bool = True


@dataclass
class Receiver:
    secret: str
    path: str = ":memory:"
    guard: Safeguards = field(default_factory=Safeguards)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS cases (alert_id TEXT PRIMARY KEY, version INTEGER, payload TEXT, status TEXT, decision TEXT);
            CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT);
            CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT, event_id TEXT);
            """
        )

    def handle(self, header: str, body: str, now: int, crash_after_commit: bool = False) -> int:
        """HTTP status for one delivery. 401: refused. 200: applied or already applied. 400: malformed."""
        if self.guard.signature and not verify(self.secret, header, body, now):
            return 401
        try:
            ev = json.loads(body)
            eid, alert, version = str(ev["event_id"]), ev["alert"], int(ev["version"])
            if ev["type"] not in ("created", "updated"):
                raise ValueError(ev["type"])
            aid = str(alert["id"])
        except (KeyError, TypeError, ValueError):
            return 400
        with self._lock:
            c = self.db
            c.execute("BEGIN IMMEDIATE")
            try:
                if self.guard.dedupe and c.execute("SELECT 1 FROM events WHERE event_id=?", (eid,)).fetchone():
                    c.execute("ROLLBACK")
                    return 200
                row = c.execute("SELECT version FROM cases WHERE alert_id=?", (aid,)).fetchone()
                stale = row is not None and self.guard.versioning and int(row[0]) > version  # same version: re-apply the snapshot
                if not stale:
                    if row is None:  # first we hear of this alert, whichever event arrived first: open its case and ticket
                        c.execute("INSERT INTO cases (alert_id, version, payload, status) VALUES (?, ?, ?, 'open')", (aid, version, json.dumps(alert, sort_keys=True)))
                        c.execute("INSERT INTO tickets (alert_id) VALUES (?)", (aid,))
                    else:
                        c.execute("UPDATE cases SET version=?, payload=? WHERE alert_id=?", (version, json.dumps(alert, sort_keys=True), aid))
                    c.execute("INSERT INTO activity (alert_id, event_id) VALUES (?, ?)", (aid, eid))
                if self.guard.dedupe:
                    c.execute("INSERT INTO events (event_id) VALUES (?)", (eid,))
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise
        if crash_after_commit:
            raise ConnectionError("receiver died before answering")
        return 200

    def cases(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT alert_id, version, payload, status, decision FROM cases ORDER BY alert_id").fetchall()
        return [{"alert_id": a, "version": v, "alert": json.loads(p), "status": s, "decision": json.loads(d) if d else None} for a, v, p, s, d in rows]

    def activity(self) -> list[tuple[str, str]]:
        return [(a, e) for a, e in self.db.execute("SELECT alert_id, event_id FROM activity ORDER BY id").fetchall()]

    def tickets(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT alert_id FROM tickets ORDER BY id").fetchall()]

    def decide(self, aid: str, decision: dict[str, Any]) -> None:
        with self._lock:
            self.db.execute("UPDATE cases SET status=?, decision=? WHERE alert_id=?", (decision["decision"], json.dumps(decision, sort_keys=True), aid))
