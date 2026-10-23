from helpers import sample
import tempfile
import unittest
from pathlib import Path

from operations import Operations
from workflow import Store, TicketConflict, load_tickets


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / "runs.db")
        self.ops = Operations(self.store)
        self.good = self.store.process(sample("DEMO-001"))
        self.exception = self.store.process(sample("DEMO-005"))

    def action(self, **changes):
        return dict(
            {
                "event_id": "review-test-001",
                "ticket_id": self.good["ticket_id"],
                "mode": "demo",
                "action": "approve_draft",
                "expected_revision": 0,
            },
            **changes,
        )

    def test_operator_can_edit_and_approve_a_draft_without_sending_it(self):
        event = self.ops.review(self.action(draft="Reviewed response draft."))
        result = self.ops.decorate(self.good)
        self.assertEqual(result["review"]["state"], "approved")
        self.assertEqual(result["review"]["draft"], "Reviewed response draft.")
        self.assertEqual(result["actions_executed"], [])
        self.assertFalse(event["replayed"])

    def test_exception_cannot_be_approved_as_a_draft(self):
        with self.assertRaises(ValueError):
            self.ops.review(self.action(ticket_id=self.exception["ticket_id"]))

    def test_exception_review_requires_a_next_step_note(self):
        action = self.action(
            ticket_id=self.exception["ticket_id"], action="mark_reviewed"
        )
        with self.assertRaises(ValueError):
            self.ops.review(action)
        result = self.ops.review(
            dict(action, note="Ask the merchant to review the high-value order.")
        )
        self.assertEqual(result["review"]["state"], "reviewed")

    def test_duplicate_review_is_replayed_but_changed_payload_is_rejected(self):
        payload = self.action()
        self.ops.review(payload)
        self.assertTrue(self.ops.review(payload)["replayed"])
        with self.assertRaises(TicketConflict):
            self.ops.review(dict(payload, note="Different decision"))

    def test_stale_operator_decision_cannot_overwrite_a_newer_review(self):
        self.ops.review(self.action())
        with self.assertRaises(TicketConflict):
            self.ops.review(
                self.action(
                    event_id="review-test-002", action="hold", note="Investigate"
                )
            )

    def test_dispatch_must_match_the_actual_saved_outcome_and_is_idempotent(self):
        payload = {
            "event_id": "n8n-test-001",
            "ticket_id": self.exception["ticket_id"],
            "mode": "demo",
            "source": "n8n",
            "destination": "draft_approval",
        }
        with self.assertRaises(ValueError):
            self.ops.dispatch(payload)
        payload["destination"] = "exceptions"
        self.ops.dispatch(payload)
        self.assertTrue(self.ops.dispatch(payload)["replayed"])
        self.assertEqual(len(self.ops.decorate(self.exception)["activity"]), 1)
