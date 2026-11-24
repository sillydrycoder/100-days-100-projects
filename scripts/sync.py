#!/usr/bin/env python3
"""Validate all projects, report coverage gaps, and regenerate registry.json, README.md, and docs/projects.json.

Zero external dependencies (Python 3 standard library only).
Usage:
    python3 scripts/sync.py           # Full sync (writes registry.json, README.md, docs/projects.json)
    python3 scripts/sync.py --status  # Print terminal progress & coverage gap report only
    python3 scripts/sync.py --check   # Strict schema validation only (CI / pre-commit friendly)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from lib import (
    DOCS_PROJECTS_PATH,
    README_PATH,
    REGISTRY_PATH,
    ascii_bar,
    compute_stats,
    discover_projects,
    format_day,
    load_config,
    utc_now_iso,
)


def print_status(config: dict[str, Any], projects: list[dict[str, Any]], stats: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    repo = config["repo"]
    bar = ascii_bar(stats["completed_count"], stats["target_total"], width=24)
    print(f"\n=== 100 Days, 100 Projects — {repo['author']} (@{repo['handle']}) ===")
    print(f"Positioning : {repo['headline']}")
    print(
        f"Progress    : [{bar}] {stats['completed_count']} / {stats['target_total']} completed "
        f"({stats['completion_pct']}%) | {stats['in_progress_count']} in-progress"
    )
    print(f"Next Day #  : Day {format_day(stats['next_day'])}")
    if stats["last_completed"]:
        lc = stats["last_completed"]
        print(f"Last Shipped: Day {lc['day_padded']} — {lc['title']} ({lc['date_completed'] or 'no date'})")
    else:
        print("Last Shipped: None yet — ready to build Day 001!")

    print("\nService Pillar Coverage Matrix:")
    print(f"  {'Pillar':<24} {'Progress':<16} {'Done/Target':<12} {'Gap':<5} Slug")
    print("  " + "-" * 84)
    for cat in stats["categories"]:
        cbar = ascii_bar(cat["completed"], cat["target"], width=12)
        ratio = f"{cat['completed']:>2}/{cat['target']:<2}"
        if cat["in_progress"]:
            ratio += f" (+{cat['in_progress']})"
        print(
            f"  {cat['short_name']:<24} [{cbar}]  {ratio:<12} {cat['remaining']:<5} {cat['slug']}"
        )

    if stats["recommended_next_categories"]:
        recs = ", ".join(stats["recommended_next_categories"])
        print(f"\nRecommended Next Upwork Pillars (largest gap): {recs}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  [!] {w}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  [X] {e}")
    else:
        print("\nValidation: OK (0 schema errors)")
    print()


def build_readme(config: dict[str, Any], projects: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    repo = config["repo"]
    tiers = config["demo_tiers"]
    cats_by_slug = {c["slug"]: c for c in stats["categories"]}

    completed = stats["completed_count"]
    target = stats["target_total"]
    badge_color = "10b981" if completed > 0 else "3b82f6"
    progress_badge = (
        f"https://img.shields.io/badge/Progress-{completed}%20%2F%20{target}%20Shipped-{badge_color}?style=for-the-badge"
    )
    pages_url = repo["pages_url"]

    lines: list[str] = [
        f"# 100 Days, 100 Projects — Production Proof-of-Work Engine",
        "",
        f"![Progress]({progress_badge})",
        "",
        f"> **{repo['author']} (`@{repo['handle']}`)** — *{repo['headline']}*",
        f">",
        f"> {repo['positioning']}",
        "",
        f"**Interactive Portfolio Hub (Filterable by Niche):** [{pages_url}]({pages_url})",
        "",
        "---",
        "",
        "## Why This Repository Exists",
        "",
        "No toy calculators or copy-paste tutorials. Every project in this catalog is derived from a **real commercial engineering requirement** (fully anonymized), built as a clean, self-contained vertical slice with:",
        "",
        "- **Architecture First:** System architecture diagram, clear module boundaries, and production error/idempotency handling.",
        "- **Zero-Friction Evaluation (`DEMO_MODE=true`):** Runs locally in **one command (`./run.sh`)** with realistic anonymized seed data and offline mock LLM/webhook fallbacks — no paid API keys required to verify.",
        "- **Free-First Live Demos + Permanent Local Fallback:** Static/cloud apps deployed on free tiers (GitHub Pages, Hugging Face Spaces, Streamlit Cloud) alongside permanent local runners and visual case studies.",
        "",
        "---",
        "",
        "## Service Pillar Coverage Matrix",
        "",
        "| Service Pillar | Progress | Completed | Focus Stack | Filtered Hub Link |",
        "| :--- | :--- | :-: | :--- | :--- |",
    ]

    for cat in stats["categories"]:
        bar = ascii_bar(cat["completed"], cat["target"], width=10)
        skills = ", ".join(f"`{s}`" for s in cat["skills"][:4])
        filter_url = f"{pages_url}?category={cat['slug']}"
        count_str = f"**{cat['completed']}** / {cat['target']}"
        if cat["in_progress"]:
            count_str += f" *(+{cat['in_progress']} wip)*"
        lines.append(
            f"| **{cat['name']}** | `{bar}` ({cat['pct']}%) | {count_str} | {skills} | [View Pillar]({filter_url}) |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Project Catalog",
            "",
        ]
    )

    if not projects:
        lines.extend(
            [
                "> **Challenge Initialized — Day 001 Launching Next.**",
                ">",
                "> The repository architecture, starter kits, automation CLI, and live GitHub Pages Portfolio Hub are live. Projects will appear here automatically as each day ships.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| Day | Project | Pillar | Stack | Demo | Status |",
                "| :-: | :--- | :--- | :--- | :--- | :-: |",
            ]
        )
        for p in projects:
            cat_short = cats_by_slug.get(p["category"], {}).get("short_name", p["category"])
            stack_str = ", ".join(f"`{s}`" for s in p["stack"][:4])
            case_link = f"[**{p['title']}**]({p['rel_path']}/README.md)"
            if p["live_url"]:
                demo_cell = f"[Live Demo]({p['live_url']}) · `{p['local_run_cmd']}`"
            else:
                tier_short = tiers.get(p["demo_tier"], {}).get("short", "Local")
                demo_cell = f"{tier_short} (`{p['local_run_cmd']}`)"
            status_cell = "Shipped" if p["status"] == "completed" else "In Progress"
            lines.append(
                f"| `{p['day_padded']}` | {case_link} | {cat_short} | {stack_str} | {demo_cell} | {status_cell} |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Quick Start (Clone & Run Any Project Locally)",
            "",
            "```bash",
            f"git clone {repo['github_url']}.git",
            "cd 100-days-100-projects/projects/day-001-<project-slug>",
            "./run.sh",
            "```",
            "",
            "---",
            "",
            "## Maintainer & 10-Year Resumability Docs",
            "",
            "- **[START_HERE.md](START_HERE.md)** — Plain-English guide to resume after days or years away.",
            "- **[AGENTS.md](AGENTS.md)** — Operating contract for AI coding assistants.",
            "- **Zero-Dependency Tooling (`scripts/`):** `sync.py --status`, `new_day.py`, and `pitch.py` run on standard-library Python 3 with zero external packages.",
            "",
            "<!-- Auto-generated by scripts/sync.py. Edit project.json files, not this README directly. -->",
            "",
        ]
    )

    return "\n".join(lines)


def write_outputs(config: dict[str, Any], projects: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    generated_at = utc_now_iso()
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "repo": config["repo"],
        "demo_tiers": config["demo_tiers"],
        "stats": stats,
        "projects": projects,
    }

    REGISTRY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    DOCS_PROJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PROJECTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    README_PATH.write_text(build_readme(config, projects, stats), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and sync the 100 Days, 100 Projects catalog.")
    parser.add_argument("--status", action="store_true", help="Display progress and coverage gaps without modifying files")
    parser.add_argument("--check", action="store_true", help="Validate project schemas strictly and exit non-zero on errors")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    projects, errors, warnings = discover_projects(config)
    stats = compute_stats(config, projects)

    if args.status:
        print_status(config, projects, stats, errors, warnings)
        return 1 if errors else 0

    if args.check:
        if errors:
            print("Schema validation FAILED:", file=sys.stderr)
            for err in errors:
                print(f"  [X] {err}", file=sys.stderr)
            return 1
        print(
            f"Schema validation PASSED ({stats['completed_count']} completed, "
            f"{stats['in_progress_count']} in-progress, {len(warnings)} warning(s))."
        )
        for w in warnings:
            print(f"  [!] {w}")
        return 0

    if errors:
        print("Sync aborted due to validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  [X] {err}", file=sys.stderr)
        return 1

    write_outputs(config, projects, stats)
    print(
        f"Synced successfully: {stats['completed_count']}/{stats['target_total']} completed "
        f"({stats['in_progress_count']} in-progress)."
    )
    print("Updated: registry.json, README.md, docs/projects.json")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  [!] {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
