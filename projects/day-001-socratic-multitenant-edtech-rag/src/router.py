"""Cost-aware LLM/VLM Model Router and Seasonal Scale-to-Zero Cost Calculator.

Demonstrates how to keep EdTech AI infrastructure near-$0 across 165 vacation days
while minimizing expensive Vision Language Model (VLM) token spend via Vision-to-JSON caching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REASONING_KEYWORDS = (
    "derive",
    "proof",
    "prove",
    "equation",
    "calculate",
    "velocity",
    "acceleration",
    "displacement",
    "incline",
    "ramp",
    "atp",
    "yield",
    "integral",
    "quadratic",
)

# Realistic per-turn token + inference economics (USD)
TIER_PRICING = {
    "text-fast": {
        "model_label": "Serverless Fast Text (Gemini 2.5 Flash-Lite / Llama-3.1-8B)",
        "est_cost_usd": 0.00022,
        "est_latency_ms": 380,
    },
    "text-reasoning": {
        "model_label": "Serverless Reasoning Text (GPT-4o-mini / DeepSeek-R1-Distill)",
        "est_cost_usd": 0.00075,
        "est_latency_ms": 740,
    },
    "vision-vlm": {
        "model_label": "Serverless Vision VLM (Gemini 2.5 Flash Vision / Qwen2.5-VL-72B)",
        "est_cost_usd": 0.00380,
        "est_latency_ms": 1650,
    },
    "vision-cache+text-fast": {
        "model_label": "Cached Diagram JSON -> Fast Text LLM (Zero Vision Tokens Re-Sent)",
        "est_cost_usd": 0.00028,
        "est_latency_ms": 410,
    },
}


@dataclass(frozen=True)
class RoutingDecision:
    tier: str
    model_label: str
    reason: str
    est_cost_usd: float
    est_latency_ms: int
    vision_savings_pct: float


def route_request(query: str, has_diagram: bool, vision_cache_hit: bool) -> RoutingDecision:
    """Select the cheapest model tier capable of answering accurately."""
    if has_diagram:
        if vision_cache_hit:
            tier = "vision-cache+text-fast"
            cfg = TIER_PRICING[tier]
            savings = round((1.0 - cfg["est_cost_usd"] / TIER_PRICING["vision-vlm"]["est_cost_usd"]) * 100, 1)
            return RoutingDecision(
                tier=tier,
                model_label=cfg["model_label"],
                reason="Diagram SHA-256 matched tenant vision cache; reusing structured JSON on fast text model.",
                est_cost_usd=cfg["est_cost_usd"],
                est_latency_ms=cfg["est_latency_ms"],
                vision_savings_pct=savings,
            )
        tier = "vision-vlm"
        cfg = TIER_PRICING[tier]
        return RoutingDecision(
            tier=tier,
            model_label=cfg["model_label"],
            reason="New diagram/chart detected; invoking Vision VLM once to extract & cache structured topology.",
            est_cost_usd=cfg["est_cost_usd"],
            est_latency_ms=cfg["est_latency_ms"],
            vision_savings_pct=0.0,
        )

    q_low = query.lower()
    if any(kw in q_low for kw in REASONING_KEYWORDS) or len(query) > 160:
        tier = "text-reasoning"
        cfg = TIER_PRICING[tier]
        return RoutingDecision(
            tier=tier,
            model_label=cfg["model_label"],
            reason="Multi-step quantitative/STEM reasoning query routed to reasoning tier.",
            est_cost_usd=cfg["est_cost_usd"],
            est_latency_ms=cfg["est_latency_ms"],
            vision_savings_pct=0.0,
        )

    tier = "text-fast"
    cfg = TIER_PRICING[tier]
    return RoutingDecision(
        tier=tier,
        model_label=cfg["model_label"],
        reason="Standard conceptual textbook query routed to low-cost fast text tier.",
        est_cost_usd=cfg["est_cost_usd"],
        est_latency_ms=cfg["est_latency_ms"],
        vision_savings_pct=0.0,
    )


def estimate_seasonal_infrastructure(
    students: int = 10000,
    schools: int = 10,
    active_days: int = 200,
    idle_days: int = 165,
    turns_per_student_day: float = 4.0,
    vision_share_pct: float = 18.0,
    vision_cache_hit_pct: float = 70.0,
) -> dict[str, Any]:
    """Compare Dedicated 24/7 GPU Hosting vs. Scale-to-Zero Serverless EdTech Architecture."""
    students = max(100, min(students, 500000))
    schools = max(1, min(schools, 500))
    active_days = max(1, min(active_days, 365))
    idle_days = max(0, 365 - active_days)

    total_annual_turns = students * active_days * turns_per_student_day
    vision_turns = total_annual_turns * (vision_share_pct / 100.0)
    cached_vision_turns = vision_turns * (vision_cache_hit_pct / 100.0)
    fresh_vision_turns = vision_turns - cached_vision_turns
    text_turns = total_annual_turns - vision_turns
    reasoning_turns = text_turns * 0.30
    fast_turns = text_turns * 0.70

    # Option B: Scale-to-Zero Serverless + Tiered Routing + Vision Cache
    serverless_inference_yr = (
        fast_turns * TIER_PRICING["text-fast"]["est_cost_usd"]
        + reasoning_turns * TIER_PRICING["text-reasoning"]["est_cost_usd"]
        + fresh_vision_turns * TIER_PRICING["vision-vlm"]["est_cost_usd"]
        + cached_vision_turns * TIER_PRICING["vision-cache+text-fast"]["est_cost_usd"]
    )
    # App compute (Cloud Run / Fly.io scale-to-zero) + Serverless Postgres/pgvector (Neon) + Object Storage (R2/S3)
    active_compute_yr = (active_days / 30.0) * (18.0 + (students / 1000.0) * 6.5)
    idle_compute_yr = (idle_days / 30.0) * (9.0 + schools * 0.4)  # Near-zero storage + dormant DB only
    serverless_total_yr = serverless_inference_yr + active_compute_yr + idle_compute_yr

    # Option A: Always-On Dedicated 24/7 GPU (e.g., A100/L40S cluster scaled for peak school hours, paid all 365 days)
    gpus_needed = max(2, int((students / 4000) + 1))
    gpu_hourly_usd = 2.40  # Conservative dedicated L40S/A100 instance rate
    dedicated_gpu_yr = gpus_needed * gpu_hourly_usd * 24 * 365
    dedicated_idle_waste_yr = gpus_needed * gpu_hourly_usd * 24 * idle_days
    dedicated_app_db_yr = 420.0 * 12
    dedicated_total_yr = dedicated_gpu_yr + dedicated_app_db_yr

    savings_yr = max(0.0, dedicated_total_yr - serverless_total_yr)
    savings_pct = round((savings_yr / dedicated_total_yr) * 100, 1) if dedicated_total_yr else 0.0

    # Extra savings specifically from Vision-to-JSON cache
    vision_without_cache = vision_turns * TIER_PRICING["vision-vlm"]["est_cost_usd"]
    vision_with_cache = (
        fresh_vision_turns * TIER_PRICING["vision-vlm"]["est_cost_usd"]
        + cached_vision_turns * TIER_PRICING["vision-cache+text-fast"]["est_cost_usd"]
    )

    return {
        "inputs": {
            "students": students,
            "schools": schools,
            "active_days": active_days,
            "idle_days": idle_days,
            "turns_per_student_day": turns_per_student_day,
            "vision_share_pct": vision_share_pct,
            "vision_cache_hit_pct": vision_cache_hit_pct,
        },
        "volume": {
            "annual_turns": int(total_annual_turns),
            "fresh_vision_turns": int(fresh_vision_turns),
            "cached_vision_turns": int(cached_vision_turns),
        },
        "dedicated_24_7": {
            "gpus_provisioned": gpus_needed,
            "annual_total_usd": round(dedicated_total_yr, 2),
            "idle_vacation_waste_usd": round(dedicated_idle_waste_yr, 2),
            "avg_monthly_usd": round(dedicated_total_yr / 12.0, 2),
        },
        "serverless_scale_to_zero": {
            "annual_total_usd": round(serverless_total_yr, 2),
            "inference_annual_usd": round(serverless_inference_yr, 2),
            "active_infra_annual_usd": round(active_compute_yr, 2),
            "idle_vacation_infra_usd": round(idle_compute_yr, 2),
            "vacation_monthly_usd": round(idle_compute_yr / max(idle_days / 30.0, 1.0), 2),
            "cost_per_student_year_usd": round(serverless_total_yr / students, 2),
        },
        "savings": {
            "annual_usd": round(savings_yr, 2),
            "annual_pct": savings_pct,
            "vision_cache_annual_savings_usd": round(max(0.0, vision_without_cache - vision_with_cache), 2),
        },
    }
