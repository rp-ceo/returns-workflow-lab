"""Start both the local UI and a separate fictional order HTTP service."""

import os
from http.server import ThreadingHTTPServer

from shop_api import sandbox_shop


if __name__ == "__main__":
    with sandbox_shop() as shop:
        from app import Application, create_handler

        handler = create_handler(Application(shop=shop))
        port = int(os.environ.get("PORT", "8765"))
        print("ReturnOps desk: http://127.0.0.1:" + str(port), flush=True)
        print(
            "Orders: separate loopback HTTP service. Synthetic data only.", flush=True
        )
        ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
