"""Separate HTTP boundary for fictional orders. This is NOT a Shopify integration."""

import json
import math
import re
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from workflow import ORDER_PATTERN, load_data


class ShopHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        reference = self.path.removeprefix("/orders/")
        if not self.path.startswith("/orders/") or not ORDER_PATTERN.fullmatch(
            reference
        ):
            return self.reply({"error": "Not found"}, 404)
        _, orders = load_data()
        order = orders.get(reference)
        return self.reply(
            order if order else {"error": "Order not found"}, 200 if order else 404
        )

    def reply(self, value, status):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ShopClient:
    def __init__(self, base_url):
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or not parsed.port
            or parsed.path not in ("", "/")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("The demo shop URL must be http://127.0.0.1:PORT.")
        self.base_url = base_url.rstrip("/")

    def get_order(self, reference):
        if not isinstance(reference, str) or not ORDER_PATTERN.fullmatch(reference):
            raise RuntimeError("Invalid order reference.")
        try:
            # A loopback-only URL is configured by the operator, never by ticket/model text.
            with urllib.request.urlopen(
                self.base_url + "/orders/" + reference, timeout=3
            ) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("Oversized order response.")
            order = json.loads(raw)
            fields = {
                "order_id",
                "customer_email",
                "status",
                "delivered_at",
                "total_eur",
                "country",
                "tracking_reference",
            }
            if not isinstance(order, dict) or set(order) != fields:
                raise ValueError("Invalid order schema.")
            if order["order_id"] != reference or order["status"] not in (
                "delivered",
                "in_transit",
            ):
                raise ValueError("Unexpected order identity/status.")
            if not all(
                isinstance(order[k], str) and order[k]
                for k in ("customer_email", "country", "tracking_reference")
            ):
                raise ValueError("Missing order fields.")
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", order["customer_email"]):
                raise ValueError("Invalid customer email.")
            amount = order["total_eur"]
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not math.isfinite(amount)
                or amount < 0
            ):
                raise ValueError("Invalid order value.")
            if order["delivered_at"] is not None:
                date.fromisoformat(order["delivered_at"])
            if order["status"] == "delivered" and order["delivered_at"] is None:
                raise ValueError("Delivered order has no date.")
            return order
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError("Order service returned an error.") from None
        except (urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError):
            raise RuntimeError(
                "Order service unavailable or invalid response."
            ) from None


@contextmanager
def sandbox_shop(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), ShopHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield ShopClient("http://127.0.0.1:" + str(server.server_port))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
