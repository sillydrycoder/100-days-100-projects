"""Day {{DAY_PADDED}} — {{TITLE}} (Idempotent Webhook & Token Ledger Starter)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_demo_local_secret")
PROCESSED_EVENTS: set[str] = set()
TOKEN_BALANCES: dict[str, int] = {}


def verify_signature(raw_body: bytes, header_sig: str) -> bool:
    expected = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig)


class WebhookHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "balances": TOKEN_BALANCES, "processed": len(PROCESSED_EVENTS)})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/webhooks/stripe":
            self._send_json(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        sig = self.headers.get("X-Demo-Signature", "")

        if not verify_signature(raw_body, sig):
            self._send_json(401, {"error": "invalid_signature"})
            return

        event = json.loads(raw_body.decode("utf-8"))
        event_id = str(event.get("id", ""))
        if event_id in PROCESSED_EVENTS:
            self._send_json(200, {"status": "duplicate_ignored", "event_id": event_id, "balances": TOKEN_BALANCES})
            return

        PROCESSED_EVENTS.add(event_id)
        data = event.get("data", {})
        tenant = str(data.get("tenant_id", "unknown"))
        tokens = int(data.get("tokens_purchased", 0))
        TOKEN_BALANCES[tenant] = TOKEN_BALANCES.get(tenant, 0) + tokens
        self._send_json(200, {"status": "processed", "event_id": event_id, "balances": TOKEN_BALANCES})


def main() -> int:
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("127.0.0.1", port), WebhookHandler)
    print(f"Webhook server listening on http://127.0.0.1:{port}/webhooks/stripe (GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
