from helpers import sample
import copy
import json
import unittest
from unittest.mock import patch

from github_queue import GitHubQueue
from shop_api import ShopClient, sandbox_shop
from workflow import load_data, load_tickets, process_ticket


class ShopIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = sandbox_shop()
        cls.shop = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_http_order_lookup_produces_checked_draft(self):
        result = process_ticket(sample("DEMO-001"), order_lookup=self.shop.get_order)
        self.assertEqual(result["route"], "return_instructions_draft")
        self.assertTrue(any("HTTP" in row["detail"] for row in result["trace"]))

    def test_http_unknown_order_requires_review(self):
        result = process_ticket(sample("DEMO-012"), order_lookup=self.shop.get_order)
        self.assertEqual(result["route"], "human_review")
        self.assertIsNone(result["order"])

    def test_order_service_failure_does_not_fall_back_to_fixture(self):
        def unavailable(_):
            raise RuntimeError("Service is down")

        result = process_ticket(sample("DEMO-001"), order_lookup=unavailable)
        self.assertEqual(result["route"], "human_review")
        self.assertIsNone(result["order"])
        self.assertIsNone(result["draft"])

    def test_empty_supplied_dataset_does_not_fall_back_to_fixture(self):
        self.assertEqual(
            process_ticket(sample("DEMO-001"), orders={})["route"], "human_review"
        )

    def test_http_lookup_does_not_bypass_identity_check(self):
        result = process_ticket(sample("DEMO-007"), order_lookup=self.shop.get_order)
        self.assertIsNone(result["order"])
        self.assertIsNone(result["draft"])

    def test_client_rejects_non_loopback_targets(self):
        for address in (
            "http://example.com:80",
            "https://127.0.0.1:8766",
            "http://127.0.0.1:8766/?token=x",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                ShopClient(address)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = GitHubQueue(
            "example/returnops", "test-placeholder-not-a-real-token"
        )
        self.result = process_ticket(sample("DEMO-005"))

    def test_review_task_contains_reason_and_explicit_classifier(self):
        recorded = []

        def request(method, path, payload=None):
            recorded.append((method, path, payload))
            return (
                []
                if method == "GET"
                else {
                    "number": 1,
                    "html_url": "https://github.com/example/returnops/issues/1",
                }
            )

        self.queue._request = request
        outcome = self.queue.publish_review(self.result)
        self.assertEqual(outcome["status"], "created")
        body = recorded[-1][2]["body"]
        self.assertIn("offline rules (no LLM call)", body)
        self.assertIn(self.result["reason"], body)
        self.assertNotIn(self.queue.token, body)

    def test_repeat_search_reuses_existing_task_without_post(self):
        saved = []

        def request(method, path, payload=None):
            if method == "GET":
                return saved
            issue = {
                "number": 2,
                "html_url": "https://github.com/example/returnops/issues/2",
                "body": payload["body"],
            }
            saved.append(issue)
            return issue

        self.queue._request = request
        self.assertEqual(self.queue.publish_review(self.result)["status"], "created")
        self.assertEqual(self.queue.publish_review(self.result)["status"], "reused")
        self.assertEqual(len(saved), 1)

    def test_reusing_ticket_id_with_changed_payload_is_rejected(self):
        saved = []

        def request(method, path, payload=None):
            if method == "GET":
                return saved
            issue = {
                "number": 3,
                "html_url": "https://github.com/example/returnops/issues/3",
                "body": payload["body"],
            }
            saved.append(issue)
            return issue

        self.queue._request = request
        self.queue.publish_review(self.result)
        changed = copy.deepcopy(self.result)
        changed["ticket"]["message"] += " Different content."
        with self.assertRaises(RuntimeError):
            self.queue.publish_review(changed)

    def test_draft_does_not_create_review_task(self):
        with patch.object(self.queue, "_request") as network:
            self.assertEqual(
                self.queue.publish_review(process_ticket(sample("DEMO-001")))["status"],
                "not_required",
            )
            network.assert_not_called()

    def test_real_addresses_are_not_published(self):
        self.result["ticket"]["sender_email"] = "person@company.test"
        with self.assertRaises(ValueError):
            self.queue.publish_review(self.result)

    def test_unknown_post_outcome_is_not_retried(self):
        with patch(
            "github_queue.urllib.request.urlopen", side_effect=TimeoutError
        ) as network:
            with self.assertRaises(RuntimeError):
                self.queue._request("POST", "/issues", {"title": "Synthetic test"})
            self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
