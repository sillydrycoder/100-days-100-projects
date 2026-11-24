"""Offline webhook replay simulator for Day {{DAY_PADDED}}."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "sample_data" / "webhook_events.json"
SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_demo_local_secret")
PORT = os.getenv("PORT", "8000")
ENDPOINT = f"http://127.0.0.1:{PORT}/webhooks/stripe"


def main() -> int:
    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    for event in events:
        body = json.dumps(event).encode("utf-8")
        sig = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json", "X-Demo-Signature": sig},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"[{resp.status}] {event['id']} ({event['type']}): {resp.read().decode('utf-8')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
