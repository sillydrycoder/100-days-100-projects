"""Comprehensive automated test suite for Day 001 (zero external dependencies)."""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from chunker import parse_textbook_markdown
from privacy import redact_pii
from router import estimate_seasonal_infrastructure
from server import create_server
from socratic_graph import SocraticTutorGraph
from storage import MultiTenantStore, TenantContext


class TestEdTechRAGPlatform(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MultiTenantStore(":memory:")
        self.store.seed_sample_data()
        self.graph = SocraticTutorGraph(self.store)
        self.oakridge = TenantContext("sch_oakridge")
        self.crestview = TenantContext("sch_crestview")

    def tearDown(self) -> None:
        self.store.close()

    def test_hierarchical_chunker_preserves_atomic_tables_equations_and_diagrams(self) -> None:
        raw = (PROJECT_DIR / "sample_data" / "textbook_physics_grade10.md").read_text(encoding="utf-8")
        chunks = parse_textbook_markdown("Physics 10", "Physics", "Grade 10", raw)
        types = [c.block_type for c in chunks]
        self.assertIn("prose", types)
        self.assertIn("equation", types)
        self.assertIn("table", types)
        self.assertIn("diagram", types)
        # Ensure equation and table chunks remain intact and carry chapter/section metadata
        eq_chunks = [c for c in chunks if c.block_type == "equation"]
        self.assertTrue(all("$$" in c.content and "Chapter" in c.parent_context for c in eq_chunks))
        tbl_chunks = [c for c in chunks if c.block_type == "table"]
        self.assertTrue(all(len(c.content.splitlines()) >= 4 for c in tbl_chunks))

    def test_strict_multi_tenant_isolation_across_schools(self) -> None:
        # Oakridge has Physics only; Crestview has Biology only.
        oak_reply = self.graph.invoke(
            tenant=self.oakridge,
            session_id="iso_1",
            student_ref="STU-201",
            query="Explain oxidative phosphorylation ATP yield and enzyme denaturation at 37 C.",
        )
        crest_reply = self.graph.invoke(
            tenant=self.crestview,
            session_id="iso_2",
            student_ref="STU-601",
            query="Explain oxidative phosphorylation ATP yield and enzyme denaturation at 37 C.",
        )
        self.assertEqual(len(oak_reply["citations"]), 0, "School A must never retrieve School B's Biology chunks")
        self.assertGreater(len(crest_reply["citations"]), 0, "School B must retrieve its own Biology chunks")

        # Diagram belonging to Crestview cannot be used by Oakridge
        cross_diag = self.graph.invoke(
            tenant=self.oakridge,
            session_id="iso_3",
            student_ref="STU-201",
            query="Read this enzyme curve.",
            diagram_id="diag_enzyme_curve",
        )
        self.assertIsNone(cross_diag["vision_structured"])

    def test_bulk_csv_onboarding_and_validation(self) -> None:
        csv_payload = "\n".join(
            [
                "external_id,role,grade_level,class_section,display_name,email",
                "STU-990,student,Grade 10,10-A Physics,Liam Vance,l.vance@oakridge.example.edu",
                "BAD-991,wizard,Grade 10,10-A,Invalid Role,bad@oakridge.example.edu",
            ]
        )
        res = self.store.import_roster_csv(self.oakridge, csv_payload)
        self.assertEqual(res["inserted"], 1)
        self.assertEqual(len(res["errors"]), 1)

        # Ensure new Oakridge student is invisible to Crestview
        crest_ids = {u["external_id"] for u in self.store.list_users(self.crestview)}
        self.assertNotIn("STU-990", crest_ids)

    def test_vision_routing_cache_hit_and_socratic_hint_ladder(self) -> None:
        turn1 = self.graph.invoke(
            tenant=self.oakridge,
            session_id="vis_sess",
            student_ref="STU-201",
            query="How do I find total displacement on this velocity-time graph?",
            diagram_id="diag_vt_graph",
        )
        self.assertEqual(turn1["routing"]["tier"], "vision-vlm")
        self.assertFalse(turn1["routing"]["vision_cache_hit"])
        self.assertEqual(turn1["hint_level"], 1)
        self.assertNotIn("140 m", turn1["response"], "Hint 1 must never leak direct numeric answer")

        turn2 = self.graph.invoke(
            tenant=self.oakridge,
            session_id="vis_sess",
            student_ref="STU-201",
            query="I see triangles and a rectangle. How do I compute the first triangle?",
            diagram_id="diag_vt_graph",
        )
        self.assertEqual(turn2["routing"]["tier"], "vision-cache+text-fast")
        self.assertTrue(turn2["routing"]["vision_cache_hit"])
        self.assertGreater(turn2["routing"]["vision_savings_pct"], 85.0)
        self.assertEqual(turn2["hint_level"], 2)
        self.assertNotIn("140 m", turn2["response"], "Hint 2 must never leak direct numeric answer")

    def test_ferpa_coppa_pii_redaction(self) -> None:
        raw = "My name is Aiden Brooks (STU-201), email a.brooks@oakridge.example.edu, phone 555-312-9000."
        res = redact_pii(raw, known_names=["Aiden Brooks"])
        self.assertTrue(res.pii_detected)
        self.assertNotIn("Aiden Brooks", res.redacted_text)
        self.assertNotIn("a.brooks@oakridge.example.edu", res.redacted_text)
        self.assertNotIn("STU-201", res.redacted_text)
        self.assertNotIn("555-312-9000", res.redacted_text)

    def test_seasonal_cost_estimator_prefers_scale_to_zero(self) -> None:
        est = estimate_seasonal_infrastructure(students=100000, schools=50, active_days=200)
        self.assertGreater(est["savings"]["annual_pct"], 25.0)
        self.assertLess(
            est["serverless_scale_to_zero"]["vacation_monthly_usd"],
            est["dedicated_24_7"]["avg_monthly_usd"] * 0.05,
        )

    def test_http_api_end_to_end(self) -> None:
        os.environ["QUIET_LOGS"] = "true"
        server, store = create_server(host="127.0.0.1", port=0, db_path=":memory:")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")
                self.assertEqual(health["schools_loaded"], 2)

            payload = json.dumps(
                {
                    "school_id": "sch_oakridge",
                    "session_id": "http_sess",
                    "student_ref": "STU-201",
                    "query": "Explain velocity-time graph slope",
                    "diagram_id": "diag_vt_graph",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/tutor/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                chat = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(chat["routing"]["tier"], "vision-vlm")
                self.assertEqual(len(chat["graph_trace"]), 7)
        finally:
            server.shutdown()
            server.server_close()
            store.close()


if __name__ == "__main__":
    unittest.main()
