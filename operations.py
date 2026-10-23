"""Operator decisions and orchestration receipts, separate from model classification."""

import hashlib
from contextlib import closing
import json
import re
import sqlite3
from datetime import datetime, timezone

from workflow import (
    TicketConflict,
    process_ticket,
    processing_failed,
    ticket_key,
    ticket_lock,
)


class Operations:
    def __init__(self, store):
        self.store = store
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS ops_events ("
                "event_id TEXT PRIMARY KEY, run_key TEXT NOT NULL, "
                "payload_hash TEXT NOT NULL, event TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )

    def _base(self, db, mode, ticket_id):
        key = ticket_key(mode, ticket_id)
        row = db.execute("SELECT result FROM runs WHERE run_key=?", (key,)).fetchone()
        if not row:
            raise ValueError("Case not found. Process the request first.")
        return key, json.loads(row[0])

    def _events(self, db, key):
        return [
            json.loads(row[0])
            for row in db.execute(
                "SELECT event FROM ops_events WHERE run_key=? ORDER BY created_at,event_id",
                (key,),
            )
        ]

    def decorate(self, result):
        attempt = result.get("attempt", 1)
        key = ticket_key(result["mode"], result["ticket_id"])
        with closing(sqlite3.connect(self.store.path)) as db, db:
            events = self._events(db, key)
            attempts = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT result FROM run_attempts WHERE run_key=? ORDER BY attempt",
                    (key,),
                )
            ]
        review = {
            "state": (
                "needs_review" if result["route"] == "human_review" else "draft_ready"
            ),
            "revision": 0,
            "note": "",
            "draft": result["draft"],
        }
        dispatch = None
        for event in events:
            if event.get("attempt", 1) != attempt:
                continue
            if event["kind"] == "review":
                review = event["review"]
            elif event["kind"] == "dispatch":
                dispatch = event
        return dict(
            result,
            attempt=attempt,
            can_reprocess=processing_failed(result),
            attempts=attempts or [dict(result, attempt=attempt)],
            activity=events,
            review=review,
            dispatch=dispatch,
        )

    def list_runs(self):
        return [self.decorate(result) for result in self.store.list_runs()]

    @staticmethod
    def _identity(payload, kind):
        if not isinstance(payload, dict):
            raise ValueError("An action must be an object.")
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,120}", event_id
        ):
            raise ValueError(
                "Provide a stable event ID of 8-120 letters, digits, hyphens or underscores."
            )
        digest = hashlib.sha256(
            json.dumps({"kind": kind, "payload": payload}, sort_keys=True).encode()
        ).hexdigest()
        key = ticket_key(payload.get("mode"), payload.get("ticket_id"))
        return event_id, digest, key

    @staticmethod
    def _check_attempt(payload, result):
        expected = payload.get("expected_attempt", 1)
        if type(expected) is not int or expected != result.get("attempt", 1):
            raise TicketConflict(
                "This case has a newer processing attempt. Refresh before acting."
            )

    @staticmethod
    def _check_revision(payload, events, attempt):
        revision = sum(
            event["kind"] == "review" and event.get("attempt", 1) == attempt
            for event in events
        )
        expected = payload.get("expected_revision")
        if type(expected) is not int or expected != revision:
            raise TicketConflict(
                "Another decision changed this case. Refresh before reviewing it."
            )
        return revision

    def _record(self, payload, kind):
        event_id, digest, key = self._identity(payload, kind)
        with (
            ticket_lock(self.store.path, key),
            closing(sqlite3.connect(self.store.path, timeout=30)) as db,
            db,
        ):
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_hash,event FROM ops_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing:
                if digest != existing[0]:
                    raise TicketConflict(
                        "This event ID was already used with different content."
                    )
                return dict(json.loads(existing[1]), replayed=True)
            key, result = self._base(db, payload.get("mode"), payload.get("ticket_id"))
            self._check_attempt(payload, result)
            attempt = result.get("attempt", 1)
            now = datetime.now(timezone.utc).isoformat()
            event = {
                "event_id": event_id,
                "ticket_id": result["ticket_id"],
                "mode": result["mode"],
                "kind": kind,
                "attempt": attempt,
                "created_at": now,
            }
            if kind == "dispatch":
                target = (
                    "exceptions"
                    if result["route"] == "human_review"
                    else "draft_approval"
                )
                if (
                    payload.get("destination") != target
                    or payload.get("source") != "n8n"
                ):
                    raise ValueError(
                        "The dispatch destination must match the saved decision."
                    )
                event.update(
                    source="n8n",
                    destination=target,
                    detail="n8n routed this saved outcome to " + target + ".",
                )
            else:
                revision = self._check_revision(payload, self._events(db, key), attempt)
                note = payload.get("note", "")
                draft = payload.get("draft", result["draft"])
                action = payload.get("action")
                if not isinstance(note, str) or len(note) > 1500:
                    raise ValueError("The note must be text, up to 1500 characters.")
                if action == "approve_draft":
                    if result["route"] == "human_review" or not result["draft"]:
                        raise ValueError(
                            "An exception cannot be approved as an automatic draft."
                        )
                    if (
                        not isinstance(draft, str)
                        or not 1 <= len(draft.strip()) <= 4000
                    ):
                        raise ValueError("A non-empty draft is required.")
                    state = "approved"
                elif action == "mark_reviewed":
                    if result["route"] != "human_review" or not note.strip():
                        raise ValueError(
                            "Reviewing an exception requires a note describing the next step."
                        )
                    state = "reviewed"
                elif action == "hold":
                    if not note.strip():
                        raise ValueError(
                            "Explain why the case needs further investigation."
                        )
                    state = "needs_review"
                else:
                    raise ValueError("Unknown review action.")
                event.update(
                    actor="Demo operator",
                    action=action,
                    detail=note.strip()
                    or "Response draft approved for sending; nothing sent.",
                    review={
                        "state": state,
                        "revision": revision + 1,
                        "note": note.strip(),
                        "draft": draft,
                    },
                )
            db.execute(
                "INSERT INTO ops_events VALUES (?,?,?,?,?)",
                (event_id, key, digest, json.dumps(event), now),
            )
            return dict(event, replayed=False)

    @staticmethod
    def _retry_replay(db, event_id, digest):
        row = db.execute(
            "SELECT payload_hash,run_key,event FROM ops_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != digest:
            raise TicketConflict(
                "This event ID was already used with different content."
            )
        event = json.loads(row[2])
        result = db.execute(
            "SELECT result FROM run_attempts WHERE run_key=? AND attempt=?",
            (row[1], event["attempt"]),
        ).fetchone()
        return dict(json.loads(result[0]), replayed=True)

    def reprocess(self, payload, **options):
        event_id, digest, key = self._identity(payload, "reprocess")
        fields = {
            "event_id",
            "ticket_id",
            "mode",
            "expected_attempt",
            "expected_revision",
            "note",
        }
        if set(payload) != fields:
            raise ValueError(
                "Retry needs identifiers, attempt, review revision and a note."
            )
        note = payload.get("note")
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1500:
            raise ValueError(
                "Explain why processing should be retried (1-1500 characters)."
            )
        with ticket_lock(self.store.path, key):
            with closing(sqlite3.connect(self.store.path)) as db:
                replay = self._retry_replay(db, event_id, digest)
                if replay is not None:
                    return replay
                _, previous = self._base(db, payload["mode"], payload["ticket_id"])
                self._check_attempt(payload, previous)
                old_attempt = previous.get("attempt", 1)
                self._check_revision(payload, self._events(db, key), old_attempt)
                if not processing_failed(previous):
                    raise ValueError(
                        "Only a model or order-service failure can be retried."
                    )

            # No database lock is held while calling the model or order service.
            result = process_ticket(previous["ticket"], previous["mode"], **options)
            result["attempt"] = old_attempt + 1
            now = datetime.now(timezone.utc).isoformat()
            event = {
                "event_id": event_id,
                "ticket_id": previous["ticket_id"],
                "mode": previous["mode"],
                "kind": "reprocess",
                "from_attempt": old_attempt,
                "attempt": result["attempt"],
                "created_at": now,
                "detail": note.strip(),
            }
            with closing(sqlite3.connect(self.store.path, timeout=30)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                replay = self._retry_replay(db, event_id, digest)
                if replay is not None:
                    return replay
                _, current = self._base(db, payload["mode"], payload["ticket_id"])
                if current != previous:
                    raise TicketConflict(
                        "Processing changed elsewhere. Refresh this case."
                    )
                # A second server process may have recorded a review during the call.
                self._check_revision(payload, self._events(db, key), old_attempt)
                db.execute(
                    "INSERT OR IGNORE INTO run_attempts VALUES (?,?,?)",
                    (key, old_attempt, json.dumps(dict(previous, attempt=old_attempt))),
                )
                db.execute(
                    "INSERT INTO run_attempts VALUES (?,?,?)",
                    (key, result["attempt"], json.dumps(result)),
                )
                db.execute(
                    "UPDATE runs SET result=?,created_at=? WHERE run_key=?",
                    (json.dumps(result), result["created_at"], key),
                )
                db.execute(
                    "INSERT INTO ops_events VALUES (?,?,?,?,?)",
                    (event_id, key, digest, json.dumps(event), now),
                )
            return dict(result, replayed=False)

    def review(self, payload):
        return self._record(payload, "review")

    def dispatch(self, payload):
        return self._record(payload, "dispatch")
