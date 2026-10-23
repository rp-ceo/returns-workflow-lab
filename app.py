"""Local operations desk and JSON API."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from operations import Operations
from shop_api import ShopClient
from workflow import ROOT, Store, TicketConflict, load_data, load_tickets

STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/style.css": ("style.css", "text/css"),
    "/app.js": ("app.js", "application/javascript"),
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
)


class Application:
    def __init__(
        self,
        store=None,
        shop=None,
        extractor=None,
        live_available=None,
        reports_dir=None,
    ):
        self.store = (
            store if store is not None else Store(ROOT / "runtime/runs.sqlite3")
        )
        self.ops = Operations(self.store)
        self.shop = shop
        self.extractor = extractor
        self.live_available = live_available
        self.reports_dir = (
            Path(reports_dir) if reports_dir else ROOT / "runtime/reports"
        )

    def has_live_model(self):
        if self.live_available is not None:
            return self.live_available
        return bool(os.environ.get("OPENAI_API_KEY"))

    def processing_options(self, mode):
        options = {}
        if self.shop is not None:
            options["order_lookup"] = self.shop.get_order
        if mode == "live" and self.extractor is not None:
            options["extractor"] = self.extractor
        return options

    def process(self, raw_ticket, mode):
        result = self.store.process(raw_ticket, mode, **self.processing_options(mode))
        return self.ops.decorate(result)

    def reprocess(self, payload, mode):
        result = self.ops.reprocess(payload, **self.processing_options(mode))
        return self.ops.decorate(result)

    def state(self):
        policy, orders = load_data()
        runs = self.ops.list_runs()
        receipts = [
            {
                "ticket_id": run["ticket_id"],
                "destination": run["dispatch"]["destination"],
                "created_at": run["dispatch"]["created_at"],
            }
            for run in runs
            if run["dispatch"]
        ]
        report = self.reports_dir / "evaluation-live.json"
        try:
            evaluation = json.loads(report.read_text())
            if not isinstance(evaluation, dict) or not isinstance(
                evaluation.get("cases"), list
            ):
                evaluation = None
        except (OSError, ValueError):
            evaluation = None
        return {
            "policy": policy,
            "runs": runs,
            "samples": load_tickets(),
            "live_available": self.has_live_model(),
            "order_count": len(orders),
            "order_source": "Sandbox HTTP API" if self.shop else "Local fixtures",
            "evaluation": evaluation,
            "orchestration": {"runs": receipts} if receipts else None,
        }


class Handler(BaseHTTPRequestHandler):
    application = None

    def reply(self, value, status=200, content_type="application/json"):
        if isinstance(value, str):
            raw = value.encode()
        else:
            raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            route = urlparse(self.path).path
            if route == "/api/state":
                return self.reply(self.application.state())
            if route == "/api/workflow":
                path = ROOT / "automation/n8n/returns-triage.json"
                return self.reply(json.loads(path.read_text()))
            if route in STATIC_FILES:
                name, kind = STATIC_FILES[route]
                return self.reply((ROOT / "web" / name).read_text(), content_type=kind)
            return self.reply({"error": "Not found"}, 404)
        except Exception:
            return self.reply({"error": "The request could not be completed."}, 500)

    def read_payload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length.") from None
        if not 0 < length <= 12000:
            raise ValueError("Request body must be between 1 and 12000 bytes.")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("The request body must be an object.")
        return payload

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self.reply({"error": "Cross-origin requests are not accepted."}, 403)
        if self.headers.get_content_type() != "application/json":
            return self.reply({"error": "Use application/json."}, 415)
        try:
            payload = self.read_payload()
            route = urlparse(self.path).path
            app = self.application
            if route == "/api/review":
                return self.reply(app.ops.review(payload))
            if route == "/api/dispatch":
                return self.reply(app.ops.dispatch(payload))
            if route not in ("/api/process", "/api/demo", "/api/reprocess"):
                return self.reply({"error": "Not found"}, 404)
            mode = payload.get("mode", "demo")
            if mode not in ("demo", "live"):
                raise ValueError("Mode must be demo or live.")
            if mode == "live" and not app.has_live_model():
                raise ValueError(
                    "Live mode is not configured. Use demo mode without an API key."
                )
            if route == "/api/process":
                return self.reply(app.process(payload.get("ticket"), mode))
            if route == "/api/reprocess":
                return self.reply(app.reprocess(payload, mode))
            if mode != "demo":
                raise ValueError(
                    "Batch demo uses the offline classifier. Submit live tickets individually."
                )
            results = [app.process(ticket, "demo") for ticket in load_tickets()]
            return self.reply({"results": results})
        except TicketConflict as error:
            return self.reply({"error": str(error)}, 409)
        except ValueError as error:
            message = (
                str(error) if type(error) is ValueError else "Invalid JSON request."
            )
            return self.reply({"error": message}, 400)
        except (TypeError, KeyError):
            return self.reply({"error": "Invalid request fields."}, 400)
        except Exception:
            return self.reply({"error": "The request could not be completed."}, 500)

    def log_message(self, format, *args):
        # Do not put customer text or credentials in access logs.
        pass


def create_handler(application):
    class BoundHandler(Handler):
        pass

    BoundHandler.application = application
    return BoundHandler


if __name__ == "__main__":
    shop_url = os.environ.get("ORDER_API_URL")
    shop = ShopClient(shop_url) if shop_url else None
    port = int(os.environ.get("PORT", "8765"))
    handler = create_handler(Application(shop=shop))
    print(f"ReturnOps desk: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
