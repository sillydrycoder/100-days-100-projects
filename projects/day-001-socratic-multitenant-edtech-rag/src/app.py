#!/usr/bin/env python3
"""Day 001 Entry Point — Multi-Tenant Socratic EdTech RAG & Vision-Routing Tutor.

Usage:
    ./run.sh                    # Starts interactive web console at http://127.0.0.1:8000
    ./run.sh --smoke-test       # Runs non-interactive architecture smoke demo & exits 0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure sibling modules resolve cleanly regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))

from router import estimate_seasonal_infrastructure
from server import create_server
from socratic_graph import SocraticTutorGraph
from storage import MultiTenantStore, TenantContext


def run_smoke_demo() -> int:
    store = MultiTenantStore(":memory:")
    store.seed_sample_data()
    graph = SocraticTutorGraph(store)

    oakridge = TenantContext("sch_oakridge")
    crestview = TenantContext("sch_crestview")

    # 1. Vision Cache Miss (first diagram query) + PII Redaction
    turn_1 = graph.invoke(
        tenant=oakridge,
        session_id="smoke_sess_1",
        student_ref="STU-201",
        query="Hi, I am Aiden Brooks (a.brooks@oakridge.example.edu). How do I find total displacement from this velocity-time graph?",
        diagram_id="diag_vt_graph",
    )

    # 2. Vision Cache Hit (follow-up turn on same diagram -> routed to cheap text model!)
    turn_2 = graph.invoke(
        tenant=oakridge,
        session_id="smoke_sess_1",
        student_ref="STU-201",
        query="I see two triangles and a rectangle in the middle. What formula gives the first triangle's area?",
        diagram_id="diag_vt_graph",
    )

    # 3. Cross-tenant Isolation Check (Oakridge Physics student asking about Crestview Biology enzyme denaturation)
    isolation_turn = graph.invoke(
        tenant=oakridge,
        session_id="smoke_sess_iso",
        student_ref="STU-201",
        query="Explain enzyme denaturation at 37 C and oxidative phosphorylation ATP yield.",
    )

    # 4. School B (Crestview Biology) asking the SAME query -> retrieves Crestview's textbook!
    crestview_turn = graph.invoke(
        tenant=crestview,
        session_id="smoke_sess_bio",
        student_ref="STU-601",
        query="Explain enzyme denaturation at 37 C and oxidative phosphorylation ATP yield.",
    )

    cost_projection = estimate_seasonal_infrastructure(students=100000, schools=50, active_days=200)

    summary = {
        "turn_1_vision_miss_and_pii": {
            "pii_redacted": turn_1["pii_redacted"],
            "redacted_query": turn_1["redacted_query"],
            "hint_level": turn_1["hint_level"],
            "model_tier": turn_1["routing"]["tier"],
            "vision_cache_hit": turn_1["routing"]["vision_cache_hit"],
            "est_cost_usd": turn_1["routing"]["est_cost_usd"],
            "citations": [c["label"] for c in turn_1["citations"]],
        },
        "turn_2_vision_cache_hit": {
            "hint_level": turn_2["hint_level"],
            "model_tier": turn_2["routing"]["tier"],
            "vision_cache_hit": turn_2["routing"]["vision_cache_hit"],
            "vision_savings_pct": turn_2["routing"]["vision_savings_pct"],
            "est_cost_usd": turn_2["routing"]["est_cost_usd"],
        },
        "tenant_isolation_verification": {
            "oakridge_chunks_for_biology_query": len(isolation_turn["citations"]),
            "crestview_chunks_for_biology_query": len(crestview_turn["citations"]),
            "zero_cross_tenant_leakage": len(isolation_turn["citations"]) == 0 and len(crestview_turn["citations"]) > 0,
        },
        "scale_100k_students_50_schools_projection": cost_projection["savings"],
    }
    print(json.dumps(summary, indent=2))
    store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Tenant Socratic EdTech RAG & Vision-Routing Tutor")
    parser.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", "8000")))
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", str(Path(__file__).resolve().parent.parent / "demo_edtech.db")))
    parser.add_argument("--smoke-test", action="store_true", help="Run non-interactive end-to-end demo and print JSON telemetry")
    args = parser.parse_args()

    if args.smoke_test:
        return run_smoke_demo()

    server, store = create_server(host=args.host, port=args.port, db_path=args.db)
    mode = "DEMO_MODE (offline deterministic)" if os.getenv("DEMO_MODE", "true").lower() == "true" else "LIVE LLM MODE"
    print(f"\nMulti-Tenant Socratic EdTech RAG Console running at http://{args.host}:{args.port}")
    print(f"Runtime Mode : {mode}")
    print(f"Database     : {args.db}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down cleanly.")
    finally:
        server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
