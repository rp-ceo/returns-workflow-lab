import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow import Store, TicketConflict, load_data, load_tickets, process_ticket, rule_extract


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ticket = {"ticket_id": "TEST-001", "sender_email": "alex@example.com", "message": "I would like to return ORD-1001."}

    def test_business_scenarios(self):
        for ticket in load_tickets():
            with self.subTest(ticket=ticket["ticket_id"]):
                result = process_ticket(ticket)
                self.assertEqual(result["route"], ticket["expected_route"])
                self.assertEqual(result["actions_executed"], [])

    def test_expired_return_explains_failed_window(self):
        result = process_ticket(load_tickets()[2])
        window = next(c for c in result["checks"] if c["label"] == "Within return window")
        self.assertFalse(window["passed"])
        self.assertIn("51 days", window["detail"])

    def test_thirty_day_boundary_is_inclusive(self):
        policy, orders = load_data()
        orders["ORD-1001"]["delivered_at"] = "2026-09-22"
        self.assertEqual(process_ticket(self.ticket, orders=orders)["route"], "return_instructions_draft")
        orders["ORD-1001"]["delivered_at"] = "2026-09-21"
        self.assertEqual(process_ticket(self.ticket, orders=orders)["route"], "human_review")

    def test_future_delivery_date_is_not_eligible(self):
        _, orders = load_data()
        orders["ORD-1001"]["delivered_at"] = "2026-10-23"
        self.assertEqual(process_ticket(self.ticket, orders=orders)["route"], "human_review")

    def test_not_delivered_cannot_get_return_instructions(self):
        ticket = {"ticket_id": "TRANSIT", "sender_email": "sam@example.com", "message": "I want to return ORD-1002."}
        self.assertEqual(process_ticket(ticket)["route"], "human_review")

    def test_identity_failure_does_not_disclose_order(self):
        ticket = dict(self.ticket, sender_email="someone@example.com")
        result = process_ticket(ticket)
        self.assertIsNone(result["order"])
        self.assertIsNone(result["draft"])

    def test_low_model_confidence_requires_review(self):
        extraction = dict(rule_extract(self.ticket), confidence=0.2)
        result = process_ticket(self.ticket, "live", extractor=lambda _: extraction)
        self.assertEqual(result["route"], "human_review")

    def test_hallucinated_model_order_is_rejected(self):
        extraction = dict(rule_extract(self.ticket), order_id="ORD-1006")
        result = process_ticket(self.ticket, "live", extractor=lambda _: extraction)
        self.assertEqual(result["route"], "human_review")
        self.assertIsNone(result["extraction"])

    def test_model_cannot_skip_return_policy(self):
        ticket = load_tickets()[4]
        result = process_ticket(ticket, "live", extractor=rule_extract)
        self.assertEqual(result["route"], "human_review")
        self.assertTrue(any(not c["passed"] for c in result["checks"]))

    def test_model_failure_falls_back_to_review(self):
        def broken(_):
            raise RuntimeError("Provider unavailable")
        result = process_ticket(self.ticket, "live", extractor=broken)
        self.assertEqual(result["route"], "human_review")

    def test_invalid_scores_are_rejected(self):
        for score in (True, float("nan"), 2, -1):
            with self.subTest(score=score):
                result = process_ticket(self.ticket, "live", extractor=lambda _, score=score: dict(rule_extract(self.ticket), confidence=score))
                self.assertEqual(result["route"], "human_review")

    def test_invented_evidence_is_rejected(self):
        extraction = dict(rule_extract(self.ticket), evidence="delivered yesterday")
        self.assertEqual(process_ticket(self.ticket, "live", extractor=lambda _: extraction)["route"], "human_review")

    def test_duplicate_does_not_call_extractor_again(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "runs.db")
            with patch("workflow.rule_extract", wraps=rule_extract) as extractor:
                first = store.process(self.ticket)
                second = store.process(self.ticket)
                self.assertFalse(first["replayed"])
                self.assertTrue(second["replayed"])
                self.assertEqual(extractor.call_count, 1)
                self.assertEqual(len(store.list_runs()), 1)

    def test_same_id_with_changed_content_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "runs.db")
            store.process(self.ticket)
            with self.assertRaises(TicketConflict):
                store.process(dict(self.ticket, message="Where is ORD-1001?"))

    def test_bad_input_is_rejected(self):
        for ticket in (None, {}, dict(self.ticket, message=""), dict(self.ticket, sender_email="not-an-email")):
            with self.subTest(ticket=ticket):
                with self.assertRaises(ValueError):
                    process_ticket(ticket)


if __name__ == "__main__":
    unittest.main()
