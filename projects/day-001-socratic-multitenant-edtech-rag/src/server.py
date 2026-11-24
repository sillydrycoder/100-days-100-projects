"""HTTP REST API and Dark-Mode Interactive Console Server for Day 001.

Zero external dependencies (Python 3 stdlib HTTPServer + SQLite), ready for local ./run.sh
or 1-click container deployment to Hugging Face Spaces / Render / Cloud Run.
"""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from router import estimate_seasonal_infrastructure
from socratic_graph import SocraticTutorGraph, load_sample_diagrams
from storage import MultiTenantStore, TenantContext

WEB_DIR = Path(__file__).resolve().parent / "web"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "postgres_rls.sql"


def create_server(host: str = "127.0.0.1", port: int = 8000, db_path: str | Path = ":memory:") -> tuple[ThreadingHTTPServer, MultiTenantStore]:
    store = MultiTenantStore(db_path=db_path)
    store.seed_sample_data()
    graph = SocraticTutorGraph(store)
    diagrams = load_sample_diagrams()

    class RequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            if os.getenv("QUIET_LOGS", "false").lower() != "true":
                super().log_message(format, *args)

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _serve_static(self, rel_path: str) -> None:
            safe_rel = "index.html" if rel_path in ("", "/") else rel_path.lstrip("/")
            candidate = (WEB_DIR / safe_rel).resolve()
            if not str(candidate).startswith(str(WEB_DIR.resolve())) or not candidate.is_file():
                self.send_error(404, "Not Found")
                return
            content_type, _ = mimetypes.guess_type(str(candidate))
            body = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            try:
                if path == "/api/health":
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "mode": "demo" if os.getenv("DEMO_MODE", "true").lower() == "true" else "live",
                            "schools_loaded": len(store.list_schools()),
                        },
                    )
                    return

                if path == "/api/schools":
                    self._send_json(200, {"schools": store.list_schools()})
                    return

                if path == "/api/diagrams":
                    school_id = (qs.get("school_id") or [""])[0]
                    filtered = [d for d in diagrams if not school_id or d["school_id"] == school_id]
                    self._send_json(200, {"diagrams": filtered})
                    return

                if path == "/api/users":
                    school_id = (qs.get("school_id") or [""])[0]
                    tenant = TenantContext(school_id)
                    self._send_json(200, {"school_id": school_id, "users": store.list_users(tenant)})
                    return

                if path == "/api/chunks":
                    school_id = (qs.get("school_id") or [""])[0]
                    subject = (qs.get("subject") or [None])[0]
                    tenant = TenantContext(school_id)
                    chunks = store.list_chunks(tenant, subject=subject)
                    self._send_json(200, {"school_id": school_id, "count": len(chunks), "chunks": chunks})
                    return

                if path == "/api/turns":
                    school_id = (qs.get("school_id") or [""])[0]
                    tenant = TenantContext(school_id)
                    self._send_json(200, {"school_id": school_id, "turns": store.list_turns(tenant)})
                    return

                if path == "/api/schema/rls":
                    sql = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
                    self._send_json(200, {"sql": sql})
                    return

                if path == "/api/cost/estimate":
                    res = estimate_seasonal_infrastructure(
                        students=int((qs.get("students") or ["10000"])[0]),
                        schools=int((qs.get("schools") or ["10"])[0]),
                        active_days=int((qs.get("active_days") or ["200"])[0]),
                        turns_per_student_day=float((qs.get("turns_per_day") or ["4.0"])[0]),
                        vision_share_pct=float((qs.get("vision_pct") or ["18"])[0]),
                        vision_cache_hit_pct=float((qs.get("cache_pct") or ["70"])[0]),
                    )
                    self._send_json(200, res)
                    return

                self._serve_static(path)
            except (ValueError, KeyError) as exc:
                self._send_json(400, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                body = self._read_json()

                if path == "/api/schools":
                    created = store.upsert_school(
                        school_id=str(body.get("school_id", "")),
                        name=str(body.get("name", "")),
                        curriculum=str(body.get("curriculum", "Custom K-12")),
                        grades=list(body.get("grades", ["Grade 9", "Grade 10"])),
                        classes=list(body.get("classes", ["10-A"])),
                    )
                    self._send_json(201, {"school": created})
                    return

                if path == "/api/onboarding/csv":
                    tenant = TenantContext(str(body.get("school_id", "")))
                    csv_text = str(body.get("csv_text", ""))
                    summary = store.import_roster_csv(tenant, csv_text)
                    self._send_json(200, summary)
                    return

                if path == "/api/ingest/textbook":
                    tenant = TenantContext(str(body.get("school_id", "")))
                    result = store.ingest_textbook(
                        tenant=tenant,
                        title=str(body.get("title", "Untitled Textbook")),
                        subject=str(body.get("subject", "General")),
                        grade_level=str(body.get("grade_level", "Grade 10")),
                        raw_markdown=str(body.get("content", "")),
                    )
                    self._send_json(200, result)
                    return

                if path == "/api/tutor/chat":
                    tenant = TenantContext(str(body.get("school_id", "")))
                    reply = graph.invoke(
                        tenant=tenant,
                        session_id=str(body.get("session_id", "sess_web_01")),
                        student_ref=str(body.get("student_ref", "STU-201")),
                        query=str(body.get("query", "")),
                        subject=body.get("subject") or None,
                        grade_level=body.get("grade_level") or None,
                        diagram_id=body.get("diagram_id") or None,
                        diagram_payload_text=body.get("diagram_payload_text") or None,
                    )
                    self._send_json(200, reply)
                    return

                self._send_json(404, {"error": f"Unknown endpoint: {path}"})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": str(exc)})

    server = ThreadingHTTPServer((host, port), RequestHandler)
    return server, store
