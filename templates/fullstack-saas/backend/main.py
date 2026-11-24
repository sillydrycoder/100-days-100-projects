"""Day {{DAY_PADDED}} — {{TITLE}} (Starter API Server).

Replace or extend with FastAPI / Django / Flask as needed for the day's Upwork scope.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BASE_DIR / "sample_data" / "seed.json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/health", "/api/tenants"):
            payload = {
                "service": "{{TITLE}}",
                "mode": "demo" if os.getenv("DEMO_MODE", "true").lower() == "true" else "live",
                "data": json.loads(SEED_PATH.read_text(encoding="utf-8")),
            }
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not Found")


def main() -> int:
    port = int(os.getenv("API_PORT", "8000"))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"API listening at http://127.0.0.1:{port} (GET /health, /api/tenants)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
