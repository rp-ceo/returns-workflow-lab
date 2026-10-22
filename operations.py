"""Operator decisions and orchestration receipts, separate from model classification."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

from workflow import LOCK, TicketConflict


class Operations:
    def __init__(self, store):
        self.store = store
        with sqlite3.connect(store.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS ops_events (event_id TEXT PRIMARY KEY, run_key TEXT NOT NULL, payload_hash TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL)")

    def _base(self, db, mode, ticket_id):
        if mode not in ("demo", "live") or not isinstance(ticket_id, str) or not 1 <= len(ticket_id) <= 80:
            raise ValueError("Invalid case identifier.")
        key = mode + ":" + ticket_id
        row = db.execute("SELECT result FROM runs WHERE run_key=?", (key,)).fetchone()
        if not row:
            raise ValueError("Case not found. Process the request first.")
        return key, json.loads(row[0])

    def _events(self, db, key):
        return [json.loads(row[0]) for row in db.execute("SELECT event FROM ops_events WHERE run_key=? ORDER BY created_at,event_id", (key,))]

    def decorate(self, result):
        with sqlite3.connect(self.store.path) as db:
            events = self._events(db, result["mode"] + ":" + result["ticket_id"])
        review = {"state": "needs_review" if result["route"] == "human_review" else "draft_ready", "revision": 0, "note": "", "draft": result["draft"]}
        dispatch = None
        for event in events:
            if event["kind"] == "review":
                review = event["review"]
            else:
                dispatch = event
        return dict(result, activity=events, review=review, dispatch=dispatch)

    def list_runs(self):
        return [self.decorate(result) for result in self.store.list_runs()]

    def _record(self, payload, kind):
        if not isinstance(payload, dict):
            raise ValueError("An action must be an object.")
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", event_id):
            raise ValueError("Provide a stable event ID of 8-120 letters, digits, hyphens or underscores.")
        digest = hashlib.sha256(json.dumps({"kind": kind, "payload": payload}, sort_keys=True).encode()).hexdigest()
        with LOCK, sqlite3.connect(self.store.path, timeout=30) as db:
            existing = db.execute("SELECT payload_hash,event FROM ops_events WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                if digest != existing[0]:
                    raise TicketConflict("This event ID was already used with different content.")
                return dict(json.loads(existing[1]), replayed=True)
            key, result = self._base(db, payload.get("mode"), payload.get("ticket_id"))
            now = datetime.now(timezone.utc).isoformat()
            event = {"event_id": event_id, "ticket_id": result["ticket_id"], "mode": result["mode"], "kind": kind, "created_at": now}
            if kind == "dispatch":
                target = "exceptions" if result["route"] == "human_review" else "draft_approval"
                if payload.get("destination") != target or payload.get("source") != "n8n":
                    raise ValueError("The dispatch destination must match the saved decision.")
                event.update(source="n8n", destination=target, detail="n8n routed this saved outcome to " + target + ".")
            else:
                previous = [item for item in self._events(db, key) if item["kind"] == "review"]
                revision = len(previous)
                expected = payload.get("expected_revision")
                if isinstance(expected, bool) or not isinstance(expected, int) or expected != revision:
                    raise TicketConflict("Another decision changed this case. Refresh before reviewing it.")
                note = payload.get("note", "")
                draft = payload.get("draft", result["draft"])
                action = payload.get("action")
                if not isinstance(note, str) or len(note) > 1500:
                    raise ValueError("The note must be text, up to 1500 characters.")
                if action == "approve_draft":
                    if result["route"] == "human_review" or not result["draft"]:
                        raise ValueError("An exception cannot be approved as an automatic draft.")
                    if not isinstance(draft, str) or not 1 <= len(draft.strip()) <= 4000:
                        raise ValueError("A non-empty draft is required.")
                    state = "approved"
                elif action == "mark_reviewed":
                    if result["route"] != "human_review" or not note.strip():
                        raise ValueError("Reviewing an exception requires a note describing the next step.")
                    state = "reviewed"
                elif action == "hold":
                    if not note.strip():
                        raise ValueError("Explain why the case needs further investigation.")
                    state = "needs_review"
                else:
                    raise ValueError("Unknown review action.")
                event.update(actor="Demo operator", action=action, detail=note.strip() or "Response draft approved for sending; nothing sent.",
                             review={"state": state, "revision": revision + 1, "note": note.strip(), "draft": draft})
            db.execute("INSERT INTO ops_events VALUES (?,?,?,?,?)", (event_id, key, digest, json.dumps(event), now))
            return dict(event, replayed=False)

    def review(self, payload):
        return self._record(payload, "review")

    def dispatch(self, payload):
        return self._record(payload, "dispatch")
