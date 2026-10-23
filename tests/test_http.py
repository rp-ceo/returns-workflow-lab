import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import Application, create_handler
from helpers import sample
from workflow import Store, rule_extract


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.app = Application(
            store=Store(root / "runs.db"),
            reports_dir=root / "reports",
            extractor=rule_extract,
            live_available=False,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.app))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def request(self, method, path, payload=None, raw=None, headers=None):
        body = (
            raw
            if raw is not None
            else json.dumps(payload) if payload is not None else None
        )
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        try:
            connection.request(method, path, body, request_headers)
            response = connection.getresponse()
            raw_result = response.read().decode()
            content_type = response.getheader("Content-Type", "")
            result = (
                json.loads(raw_result)
                if "application/json" in content_type
                else raw_result
            )
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def process_sample(self, ticket_id="DEMO-001"):
        status, result, _ = self.request(
            "POST", "/api/process", {"ticket": sample(ticket_id)}
        )
        self.assertEqual(status, 200)
        return result

    def test_static_routes_and_response_headers(self):
        for path, kind in (
            ("/", "text/html"),
            ("/style.css", "text/css"),
            ("/app.js", "application/javascript"),
        ):
            with self.subTest(path=path):
                status, body, headers = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn(kind, headers["Content-Type"])
                self.assertIn(
                    "frame-ancestors 'none'", headers["Content-Security-Policy"]
                )
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_state_and_workflow_are_available_without_reports_or_api_key(self):
        status, state, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertFalse(state["live_available"])
        self.assertIsNone(state["evaluation"])
        self.assertIsNone(state["orchestration"])
        self.assertEqual(state["runs"], [])
        status, workflow, _ = self.request("GET", "/api/workflow")
        self.assertEqual(status, 200)
        self.assertTrue(workflow["nodes"])

    def test_unknown_and_path_traversal_routes_are_not_served(self):
        for path in ("/missing", "/../.env.local", "/%2e%2e/.env.local"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/missing", {})[0], 404)

    def test_cross_origin_is_rejected_but_matching_origin_is_accepted(self):
        body = {"ticket": sample("DEMO-001")}
        self.assertEqual(
            self.request(
                "POST",
                "/api/process",
                body,
                headers={"Origin": "https://other.example"},
            )[0],
            403,
        )
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(
            self.request("POST", "/api/process", body, headers={"Origin": origin})[0],
            200,
        )

    def test_request_validation(self):
        for raw in ("{broken", "[]", "null", "", "x" * 12001):
            with self.subTest(raw_length=len(raw)):
                self.assertEqual(self.request("POST", "/api/process", raw=raw)[0], 400)
        self.assertEqual(
            self.request(
                "POST", "/api/process", {}, headers={"Content-Type": "text/plain"}
            )[0],
            415,
        )
        self.assertEqual(self.request("POST", "/api/process", {})[0], 400)
        self.assertEqual(
            self.request("POST", "/api/process", {"mode": "unknown"})[0], 400
        )

    def test_processing_replay_and_changed_content_conflict(self):
        first = self.process_sample()
        second = self.process_sample()
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        changed = dict(sample("DEMO-001"), message="Where is ORD-1001?")
        self.assertEqual(
            self.request("POST", "/api/process", {"ticket": changed})[0], 409
        )

    def test_live_requires_configuration_and_provider_failure_never_makes_a_draft(self):
        payload = {"mode": "live", "ticket": sample("DEMO-001")}
        self.assertEqual(self.request("POST", "/api/process", payload)[0], 400)
        self.app.live_available = True
        status, result, _ = self.request("POST", "/api/process", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["route"], "return_instructions_draft")
        self.app.extractor = lambda _: (_ for _ in ()).throw(
            RuntimeError("Provider unavailable")
        )
        payload["ticket"] = dict(payload["ticket"], ticket_id="PROVIDER-FAILURE")
        status, result, _ = self.request("POST", "/api/process", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["route"], "human_review")
        self.assertIsNone(result["draft"])

    def test_demo_batch_is_offline_and_replayable(self):
        with patch("workflow.openai_extract") as provider:
            status, result, _ = self.request("POST", "/api/demo", {"mode": "demo"})
            self.assertEqual(status, 200)
            self.assertEqual(len(result["results"]), 14)
            self.assertEqual(len(self.app.store.list_runs()), 14)
            provider.assert_not_called()
        self.app.live_available = True
        self.assertEqual(self.request("POST", "/api/demo", {"mode": "live"})[0], 400)

    def test_reprocess_recovers_a_failed_call_and_keeps_attempt_history(self):
        self.app.live_available = True
        with patch.object(
            self.app, "extractor", side_effect=RuntimeError("Unavailable")
        ):
            status, failed, _ = self.request(
                "POST", "/api/process", {"mode": "live", "ticket": sample("DEMO-001")}
            )
        self.assertEqual(status, 200)
        self.assertTrue(failed["can_reprocess"])
        payload = {
            "event_id": "http-reprocess-001",
            "ticket_id": failed["ticket_id"],
            "mode": "live",
            "expected_attempt": 1,
            "expected_revision": 0,
            "note": "Provider recovered.",
        }
        self.app.live_available = False
        self.assertEqual(self.request("POST", "/api/reprocess", payload)[0], 400)
        self.app.live_available = True
        with patch.object(self.app, "extractor", wraps=rule_extract) as extractor:
            status, result, _ = self.request("POST", "/api/reprocess", payload)
            self.assertEqual(status, 200)
            self.assertEqual(result["attempt"], 2)
            self.assertEqual(result["route"], "return_instructions_draft")
            status, replay, _ = self.request("POST", "/api/reprocess", payload)
            self.assertEqual(status, 200)
            self.assertTrue(replay["replayed"])
            self.assertEqual(extractor.call_count, 1)
        _, state, _ = self.request("GET", "/api/state")
        self.assertEqual(len(state["runs"][0]["attempts"]), 2)
        self.assertEqual(state["runs"][0]["activity"][0]["kind"], "reprocess")
        stale = dict(payload, event_id="http-reprocess-002")
        self.assertEqual(self.request("POST", "/api/reprocess", stale)[0], 409)
        self.assertEqual(
            self.request("POST", "/api/reprocess", dict(payload, ticket={}))[0], 400
        )

    def test_operator_decision_survives_reload_and_stale_revision_is_rejected(self):
        run = self.process_sample()
        payload = {
            "event_id": "http-review-001",
            "ticket_id": run["ticket_id"],
            "mode": "demo",
            "action": "approve_draft",
            "expected_revision": 0,
            "draft": "Edited response",
            "note": "Checked order details.",
        }
        self.assertEqual(self.request("POST", "/api/review", payload)[0], 200)
        status, state, _ = self.request("GET", "/api/state")
        review = state["runs"][0]["review"]
        self.assertEqual(review["draft"], "Edited response")
        self.assertEqual(review["revision"], 1)
        self.assertEqual(review["state"], "approved")
        payload["event_id"] = "http-review-002"
        self.assertEqual(self.request("POST", "/api/review", payload)[0], 409)

    def test_dispatch_is_derived_from_saved_result_and_shown_in_state(self):
        run = self.process_sample("DEMO-005")
        payload = {
            "event_id": "http-dispatch-001",
            "ticket_id": run["ticket_id"],
            "mode": "demo",
            "source": "n8n",
            "destination": "draft_approval",
        }
        self.assertEqual(self.request("POST", "/api/dispatch", payload)[0], 400)
        payload["destination"] = "exceptions"
        self.assertEqual(self.request("POST", "/api/dispatch", payload)[0], 200)
        status, state, _ = self.request("GET", "/api/state")
        self.assertEqual(state["orchestration"]["runs"][0]["destination"], "exceptions")

    def test_unexpected_server_errors_do_not_expose_internal_details(self):
        for method, route, target in (
            ("GET", "/api/state", "state"),
            ("POST", "/api/process", "process"),
        ):
            with patch.object(
                self.app, target, side_effect=OSError("private diagnostic")
            ):
                status, result, _ = self.request(
                    method,
                    route,
                    {"ticket": sample("DEMO-001")} if method == "POST" else None,
                )
            self.assertEqual(status, 500)
            self.assertNotIn("private", result["error"])

    def test_corrupt_optional_report_does_not_break_state(self):
        self.app.reports_dir.mkdir()
        (self.app.reports_dir / "evaluation-live.json").write_text("not json")
        status, state, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertIsNone(state["evaluation"])
