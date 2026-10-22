"""Run with python3 app.py, then visit http://127.0.0.1:8765."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from workflow import ROOT, Store, TicketConflict, load_data, load_tickets

STORE = Store(ROOT / "runtime/runs.sqlite3")


class Handler(BaseHTTPRequestHandler):
    def reply(self, value, status=200, content_type="application/json"):
        raw = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/state":
            policy, orders = load_data()
            return self.reply({"policy": policy, "runs": STORE.list_runs(), "samples": load_tickets(), "live_available": bool(os.environ.get("OPENAI_API_KEY")), "order_count": len(orders)})
        files = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "application/javascript")}
        if route in files:
            name, kind = files[route]
            return self.reply((ROOT / "web" / name).read_text(), content_type=kind)
        return self.reply({"error": "Not found"}, 404)

    def do_POST(self):
        if self.headers.get("Origin") and self.headers["Origin"] != "http://" + self.headers.get("Host", ""):
            return self.reply({"error": "Cross-origin requests are not accepted."}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 12000:
                return self.reply({"error": "Request body must be between 1 and 12000 bytes."}, 400)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self.reply({"error": "Use application/json."}, 415)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("The request body must be an object.")
            mode = payload.get("mode", "demo")
            if mode not in ("demo", "live"):
                raise ValueError("Mode must be demo or live.")
            if mode == "live" and not os.environ.get("OPENAI_API_KEY"):
                return self.reply({"error": "Live mode is not configured. The demo mode works without an API key."}, 400)
            route = urlparse(self.path).path
            if route == "/api/process":
                return self.reply(STORE.process(payload.get("ticket"), mode))
            if route == "/api/demo":
                # Batch is intentionally offline; live calls require one explicit ticket submission.
                if mode != "demo":
                    raise ValueError("Batch demo uses the offline classifier. Use Process request for one live ticket.")
                results = [STORE.process(ticket, "demo") for ticket in load_tickets()]
                return self.reply({"results": results})
            return self.reply({"error": "Not found"}, 404)
        except TicketConflict as error:
            return self.reply({"error": str(error)}, 409)
        except (ValueError, TypeError, KeyError):
            return self.reply({"error": "Invalid request. Check the ticket ID, email, message and order reference."}, 400)

    def log_message(self, format, *args):
        # No payloads, customer messages or credentials in access logs.
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    print("Returns Workflow Lab: http://127.0.0.1:" + str(port), flush=True)
    print("Synthetic data only. Offline mode is ready; live AI requires OPENAI_API_KEY.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
