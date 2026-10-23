"""A retry is an explicit new attempt, never an overwrite of the old decision."""

from contextlib import nullcontext
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from helpers import sample
from operations import Operations
from workflow import Store, TicketConflict, rule_extract


def unavailable(_):
    raise RuntimeError("Provider unavailable")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / "runs.db")
        self.ops = Operations(self.store)
        self.ticket = sample("DEMO-001")
        self.failed = self.store.process(self.ticket, "live", extractor=unavailable)

    def retry(self, **changes):
        return dict(
            event_id="reprocess-test-001",
            ticket_id=self.ticket["ticket_id"],
            mode="live",
            expected_attempt=1,
            expected_revision=0,
            note="Provider recovered; retry the original message.",
            **changes,
        )

    def review(self, **changes):
        payload = {
            "event_id": "recovery-review-001",
            "ticket_id": self.ticket["ticket_id"],
            "mode": "live",
            "expected_attempt": 1,
            "expected_revision": 0,
            "action": "mark_reviewed",
            "note": "Waiting for provider recovery.",
        }
        payload.update(changes)
        return payload

    def test_explicit_retry_preserves_failure_and_old_operator_history(self):
        self.ops.review(self.review())
        payload = self.retry()
        payload["expected_revision"] = 1
        result = self.ops.reprocess(payload, extractor=rule_extract)
        saved = Operations(Store(self.store.path)).list_runs()[0]
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(saved["route"], "return_instructions_draft")
        self.assertFalse(saved["can_reprocess"])
        self.assertEqual(saved["review"]["revision"], 0)
        self.assertEqual(saved["review"]["state"], "draft_ready")
        self.assertEqual([a["attempt"] for a in saved["attempts"]], [1, 2])
        self.assertEqual(saved["attempts"][0]["processing_error"], "extraction")
        self.assertEqual(
            saved["activity"][0]["review"]["note"], "Waiting for provider recovery."
        )
        self.assertEqual(saved["activity"][1]["kind"], "reprocess")
        self.assertEqual(saved["actions_executed"], [])
        replay = self.store.process(self.ticket, "live", extractor=unavailable)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["attempt"], 2)
        with self.assertRaises(TicketConflict):
            self.store.process(dict(self.ticket, message="Changed message"), "live")

    def test_retry_id_is_replayed_without_another_provider_call(self):
        extractor = Mock(side_effect=rule_extract)
        first = self.ops.reprocess(self.retry(), extractor=extractor)
        replay = self.ops.reprocess(self.retry(), extractor=extractor)
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["attempt"], 2)
        self.assertEqual(extractor.call_count, 1)
        changed = dict(self.retry(), note="Changed instruction")
        with self.assertRaises(TicketConflict):
            self.ops.reprocess(changed, extractor=extractor)

    def test_second_failure_is_saved_and_can_be_retried_separately(self):
        self.ops.reprocess(self.retry(), extractor=unavailable)
        payload = dict(self.retry(), event_id="reprocess-test-002", expected_attempt=2)
        result = self.ops.reprocess(payload, extractor=rule_extract)
        self.assertEqual(result["attempt"], 3)
        old_replay = self.ops.reprocess(self.retry(), extractor=unavailable)
        self.assertEqual(old_replay["attempt"], 2)
        self.assertEqual(self.ops.list_runs()[0]["attempt"], 3)

    def test_stale_reviews_and_dispatch_cannot_act_on_new_attempt(self):
        self.ops.reprocess(self.retry(), extractor=rule_extract)
        for payload in (self.review(), dict(self.review(), expected_attempt=True)):
            with self.subTest(payload=payload), self.assertRaises(TicketConflict):
                self.ops.review(payload)
        with self.assertRaises(TicketConflict):
            self.ops.dispatch(
                {
                    "event_id": "stale-dispatch-001",
                    "ticket_id": self.ticket["ticket_id"],
                    "mode": "live",
                    "source": "n8n",
                    "destination": "draft_approval",
                }
            )
        event = self.ops.review(
            self.review(
                event_id="new-attempt-review",
                expected_attempt=2,
                action="approve_draft",
            )
        )
        self.assertEqual(event["attempt"], 2)
        self.assertEqual(event["review"]["revision"], 1)

    def test_old_dispatch_remains_history_but_does_not_route_the_new_attempt(self):
        payload = {
            "event_id": "failure-dispatch-001",
            "ticket_id": self.ticket["ticket_id"],
            "mode": "live",
            "source": "n8n",
            "destination": "exceptions",
            "expected_attempt": 1,
        }
        self.ops.dispatch(payload)
        self.ops.reprocess(self.retry(), extractor=rule_extract)
        self.assertIsNone(self.ops.list_runs()[0]["dispatch"])
        self.assertTrue(self.ops.dispatch(payload)["replayed"])
        payload.update(
            event_id="success-dispatch-002",
            expected_attempt=2,
            destination="draft_approval",
        )
        self.ops.dispatch(payload)
        self.assertEqual(self.ops.list_runs()[0]["dispatch"]["attempt"], 2)

    def test_invalid_retry_inputs_never_call_the_provider(self):
        no_note = dict(self.retry(), note=" ")
        extra_content = dict(
            self.retry(), ticket=dict(self.ticket, message="New message")
        )
        missing_revision = self.retry()
        del missing_revision["expected_revision"]
        with patch("operations.process_ticket") as process:
            for payload in (no_note, extra_content, missing_revision):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    self.ops.reprocess(payload)
            process.assert_not_called()

    def test_policy_reviews_and_successes_cannot_be_reprocessed(self):
        for ticket in (sample("DEMO-005"), dict(self.ticket, ticket_id="SUCCESS-001")):
            self.store.process(ticket, "live", extractor=rule_extract)
            payload = dict(self.retry(), ticket_id=ticket["ticket_id"])
            with (
                self.subTest(ticket=ticket["ticket_id"]),
                self.assertRaises(ValueError),
            ):
                self.ops.reprocess(payload, extractor=rule_extract)

    def test_newer_operator_review_blocks_a_retry_from_an_old_view(self):
        self.ops.review(self.review())
        with patch("operations.process_ticket") as process:
            with self.assertRaises(TicketConflict):
                self.ops.reprocess(self.retry())
            process.assert_not_called()

    def test_model_call_holds_no_database_or_other_ticket_lock(self):
        def extract(ticket):
            # A different ticket can commit while this provider call is in progress.
            other = dict(self.ticket, ticket_id="UNRELATED-001")
            self.store.process(other, "live", extractor=rule_extract)
            return rule_extract(ticket)

        result = self.ops.reprocess(self.retry(), extractor=extract)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(len(self.store.list_runs()), 2)

    def test_review_from_another_process_during_the_call_is_not_overwritten(self):
        def extract(ticket):
            # Other server processes have separate in-memory ticket locks.
            with patch("operations.ticket_lock", return_value=nullcontext()):
                Operations(Store(self.store.path)).review(self.review())
            return rule_extract(ticket)

        with self.assertRaises(TicketConflict):
            self.ops.reprocess(self.retry(), extractor=extract)
        saved = self.ops.list_runs()[0]
        self.assertEqual(saved["attempt"], 1)
        self.assertEqual(saved["review"]["revision"], 1)
        self.assertEqual(len(saved["attempts"]), 1)

    def test_legacy_failure_and_history_are_backfilled_without_changing_ticket_hash(
        self,
    ):
        key = "live:" + self.ticket["ticket_id"]
        legacy = dict(self.failed)
        for field in ("attempt", "processing_error", "replayed"):
            legacy.pop(field, None)
        with sqlite3.connect(self.store.path) as db:
            digest = db.execute(
                "SELECT payload_hash FROM runs WHERE run_key=?", (key,)
            ).fetchone()[0]
            db.execute(
                "UPDATE runs SET result=? WHERE run_key=?", (json.dumps(legacy), key)
            )
            db.execute("DELETE FROM run_attempts WHERE run_key=?", (key,))
        self.assertTrue(self.ops.list_runs()[0]["can_reprocess"])
        self.ops.reprocess(self.retry(), extractor=rule_extract)
        self.assertEqual(len(self.ops.list_runs()[0]["attempts"]), 2)
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT payload_hash FROM runs WHERE run_key=?", (key,)
                ).fetchone()[0],
                digest,
            )

    def test_order_service_failure_can_recover_without_reclassifying_ticket_content(
        self,
    ):
        ticket = dict(self.ticket, ticket_id="SHOP-FAILURE")
        failure = self.store.process(ticket, "demo", order_lookup=unavailable)
        self.assertEqual(failure["processing_error"], "order_lookup")
        result = self.ops.reprocess(
            dict(self.retry(), ticket_id=ticket["ticket_id"], mode="demo")
        )
        self.assertEqual(result["route"], "return_instructions_draft")
