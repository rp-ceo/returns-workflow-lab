import json
from pathlib import Path
import tempfile
import unittest

from evaluate import evaluate_cases, load_cases
from workflow import ROOT, process_ticket, rule_extract


class EvaluationTests(unittest.TestCase):
    def test_challenge_cases_keep_negation_mixed_intents_and_exceptions_covered(self):
        cases = load_cases(ROOT / "data/challenge-cases.json")
        report = evaluate_cases(cases)
        for row in report["cases"]:
            with self.subTest(case=row["id"], message=row["message"]):
                self.assertTrue(row["matched"])
                if row["expected_category"] is not None:
                    self.assertTrue(row["category_matched"])
        self.assertEqual(report["provider_calls_attempted"], 0)

    def test_route_match_does_not_conceal_a_wrong_exception_category(self):
        case = {
            "ticket_id": "METRIC-001",
            "sender_email": "alex@example.com",
            "message": "ORD-1001 was damaged and I was charged twice.",
            "expected_category": "payment_problem",
            "expected_route": "human_review",
        }

        def wrong_category(ticket, mode):
            extraction = dict(rule_extract(ticket), category="damaged_item")
            return process_ticket(ticket, mode, extractor=lambda _: extraction)

        report = evaluate_cases([case], "live", processor=wrong_category)
        self.assertEqual(report["route_matches"], 1)
        self.assertEqual(report["category_matches"], 0)
        self.assertEqual(
            report["category_confusion"],
            [{"expected": "payment_problem", "actual": "damaged_item", "count": 1}],
        )

    def test_unnecessary_escalation_and_missed_review_are_counted_separately(self):
        base = {"sender_email": "alex@example.com", "message": "Return ORD-1001."}
        cases = [
            dict(
                base, ticket_id="METRIC-002", expected_route="return_instructions_draft"
            ),
            dict(base, ticket_id="METRIC-003", expected_route="human_review"),
        ]

        def inverted(ticket, mode):
            result = process_ticket(ticket, mode)
            result["route"] = (
                "human_review"
                if ticket["ticket_id"] == "METRIC-002"
                else "return_instructions_draft"
            )
            return result

        report = evaluate_cases(cases, processor=inverted)
        self.assertEqual(report["unnecessary_escalations"], 1)
        self.assertEqual(report["review_required_but_drafted"], 1)
        self.assertEqual(report["category_case_count"], 0)
        self.assertIsNone(report["cases"][0]["category_matched"])

    def test_missing_extraction_is_a_category_miss_on_a_labelled_case(self):
        case = {
            "ticket_id": "METRIC-004",
            "sender_email": "alex@example.com",
            "message": "Return ORD-1001.",
            "expected_category": "return_request",
            "expected_route": "return_instructions_draft",
        }

        def fail(ticket, mode):
            return process_ticket(ticket, mode, extractor=lambda _: {})

        report = evaluate_cases([case], "live", processor=fail)
        self.assertEqual(report["category_matches"], 0)
        self.assertEqual(report["category_confusion"][0]["actual"], "no_extraction")
        self.assertEqual(report["unnecessary_escalations"], 1)
        self.assertEqual(report["validated_live_extractions"], 0)

    def test_custom_cases_reject_unknown_labels_and_duplicate_ids(self):
        good = {"ticket_id": "CUSTOM-001", "expected_route": "human_review"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            for value in (
                [],
                {},
                [dict(good, expected_category="invented")],
                [good, good],
            ):
                with self.subTest(value=value):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        load_cases(path)
