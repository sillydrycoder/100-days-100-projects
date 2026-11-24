#!/usr/bin/env python3
"""Scaffold the next day's self-contained Upwork reference demo.

Zero external dependencies (Python 3 standard library only).
Run interactively with:
    python3 scripts/new_day.py
Or pass flags directly:
    python3 scripts/new_day.py --category ai-agents-rag --slug support-rag --title "Support Triage RAG"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

from lib import (
    PROJECTS_DIR,
    TEMPLATES_DIR,
    compute_stats,
    discover_projects,
    format_day,
    list_templates,
    load_config,
    sanitize_slug,
    today_iso,
)

TEXT_EXTENSIONS = {
    ".md",
    ".json",
    ".py",
    ".sh",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".txt",
    ".yml",
    ".yaml",
    ".example",
    ".php",
}

DEFAULT_TIER_BY_TEMPLATE = {
    "static-web": "tier-1-static",
    "python-ai-rag": "tier-2-free-app",
    "fullstack-saas": "tier-3-local-visual",
    "laravel-saas": "tier-3-local-visual",
    "api-stripe-integration": "tier-3-local-visual",
    "automation-scraper": "tier-3-local-visual",
}


def prompt_choice(label: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    print(f"\n{label}")
    for idx, (value, desc) in enumerate(options, start=1):
        marker = " (default)" if idx - 1 == default_idx else ""
        print(f"  {idx}. {value:<25} {desc}{marker}")
    while True:
        raw = input(f"Choose [1-{len(options)}] (Enter = {default_idx + 1}): ").strip()
        if not raw:
            return options[default_idx][0]
        if raw.isdigit():
            choice = int(raw) - 1
            if 0 <= choice < len(options):
                return options[choice][0]
        # Allow typing the slug directly
        for value, _ in options:
            if raw == value:
                return value
        print("Invalid selection. Enter a number or exact slug.")


def prompt_text(label: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"{label}{suffix}: ").strip()
        if val:
            return val
        if default:
            return default
        if not required:
            return ""
        print("This field is required.")


def render_placeholders(content: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def copy_template(template_dir: Path, target_dir: Path, mapping: dict[str, str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=False)
    for item in template_dir.rglob("*"):
        rel = item.relative_to(template_dir)
        dest = target_dir / rel
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix in TEXT_EXTENSIONS or item.name in {".env.example", "Dockerfile"}:
            text = item.read_text(encoding="utf-8")
            dest.write_text(render_placeholders(text, mapping), encoding="utf-8")
        else:
            shutil.copy2(item, dest)

    run_script = target_dir / "run.sh"
    if run_script.exists():
        mode = run_script.stat().st_mode
        run_script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold the next day's project folder from a stack-matched starter template."
    )
    parser.add_argument("--day", type=int, help="Override day number (defaults to next sequential day)")
    parser.add_argument("--category", help="Service pillar slug from config/categories.json")
    parser.add_argument("--slug", help="Short kebab-case project slug (e.g. support-triage-rag)")
    parser.add_argument("--title", help="Client-facing engineering project title")
    parser.add_argument("--template", help="Template folder name from templates/")
    parser.add_argument("--tier", help="Demo tier (tier-1-static | tier-2-free-app | tier-3-local-visual)")
    parser.add_argument("--stack", help="Comma-separated tech stack (e.g. Python,LangGraph,FastAPI)")
    parser.add_argument("--niche", help="Anonymized Upwork job type / use case")
    parser.add_argument("--problem", help="1-sentence business problem solved")
    parser.add_argument("--solution", help="1-sentence architecture/solution summary")
    parser.add_argument("--live-url", default="", help="Optional live demo URL if already deployed")
    parser.add_argument("--dry-run", action="store_true", help="Preview scaffold plan without writing files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    projects, errors, _ = discover_projects(config)
    if errors:
        print("Warning: existing projects have validation issues (run scripts/sync.py --check):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    stats = compute_stats(config, projects)
    categories_map = {c["slug"]: c for c in config["categories"]}
    templates = list_templates()
    tiers_map = config["demo_tiers"]

    day = args.day if args.day is not None else stats["next_day"]
    existing_days = {p["day"] for p in projects}
    if day in existing_days:
        print(f"Error: Day {format_day(day)} already exists. Choose a different --day.", file=sys.stderr)
        return 1

    interactive = not (args.category and args.slug and args.title)

    if interactive:
        print(f"\n=== Scaffolding Day {format_day(day)} / {stats['target_total']} ===")
        recs = ", ".join(stats["recommended_next_categories"]) or "none"
        print(f"Recommended pillars with largest coverage gap: {recs}")

    # 1. Category
    category = args.category
    if not category:
        cat_options = [
            (c["slug"], f"{c['short_name']} ({c['completed']}/{c['target']})")
            for c in stats["categories"]
        ]
        default_slug = (
            stats["recommended_next_categories"][0]
            if stats["recommended_next_categories"]
            else stats["categories"][0]["slug"]
        )
        default_idx = next(
            (i for i, (slug, _) in enumerate(cat_options) if slug == default_slug), 0
        )
        category = prompt_choice("Select Upwork Service Pillar:", cat_options, default_idx)
    if category not in categories_map:
        print(
            f"Error: Unknown category '{category}'. Valid options: {', '.join(categories_map)}",
            file=sys.stderr,
        )
        return 1

    cat_cfg = categories_map[category]

    # 2. Title & Slug
    title = args.title or prompt_text("Project Title (client-facing)", required=True)
    raw_slug = args.slug or prompt_text("URL/Folder Slug", default=sanitize_slug(title), required=True)
    slug = sanitize_slug(raw_slug)
    if not slug:
        print("Error: Slug cannot be empty after sanitization.", file=sys.stderr)
        return 1

    # 3. Template
    template = args.template
    if not template:
        default_tpl = cat_cfg["default_template"]
        if interactive:
            tpl_options = [(t, "Starter template") for t in templates]
            default_idx = next((i for i, (t, _) in enumerate(tpl_options) if t == default_tpl), 0)
            template = prompt_choice("Select Starter Template:", tpl_options, default_idx)
        else:
            template = default_tpl
    if template not in templates:
        print(f"Error: Unknown template '{template}'. Available: {', '.join(templates)}", file=sys.stderr)
        return 1

    # 4. Demo Tier
    tier = args.tier
    if not tier:
        default_tier = DEFAULT_TIER_BY_TEMPLATE.get(template, "tier-3-local-visual")
        if interactive:
            tier_options = [(k, v["label"]) for k, v in tiers_map.items()]
            default_idx = next((i for i, (k, _) in enumerate(tier_options) if k == default_tier), 0)
            tier = prompt_choice("Select Hosting / Demo Tier:", tier_options, default_idx)
        else:
            tier = default_tier
    if tier not in tiers_map:
        print(f"Error: Unknown demo tier '{tier}'. Valid: {', '.join(tiers_map)}", file=sys.stderr)
        return 1

    # 5. Stack & Summaries
    default_stack = ", ".join(cat_cfg["skills"][:4])
    if args.stack:
        stack = [s.strip() for s in args.stack.split(",") if s.strip()]
    elif interactive:
        raw_stack = prompt_text("Tech Stack (comma-separated)", default=default_stack, required=True)
        stack = [s.strip() for s in raw_stack.split(",") if s.strip()]
    else:
        stack = list(cat_cfg["skills"][:4])

    niche = args.niche or (
        prompt_text("Anonymized Upwork Job Type", default=f"{cat_cfg['short_name']} production demo")
        if interactive
        else f"{cat_cfg['short_name']} production demo"
    )
    problem = args.problem or (
        prompt_text("Business Problem (1 sentence)", default="TODO: Describe the anonymized client pain point.")
        if interactive
        else "TODO: Describe the anonymized client pain point."
    )
    solution = args.solution or (
        prompt_text("Architecture / Solution (1 sentence)", default="TODO: Describe the reliable backend/AI architecture built.")
        if interactive
        else "TODO: Describe the reliable backend/AI architecture built."
    )

    day_padded = format_day(day)
    folder_name = f"day-{day_padded}-{slug}"
    target_dir = PROJECTS_DIR / folder_name
    if target_dir.exists():
        print(f"Error: Destination already exists: {target_dir}", file=sys.stderr)
        return 1

    repo_cfg = config["repo"]
    project_meta: dict[str, Any] = {
        "day": day,
        "slug": slug,
        "title": title,
        "category": category,
        "status": "in-progress",
        "date_completed": "",
        "upwork_niche": niche,
        "problem": problem,
        "solution": solution,
        "stack": stack,
        "highlights": [
            "Deterministic DEMO_MODE=true works locally with zero paid API keys",
            "Clean architecture diagram and realistic anonymized sample_data/",
            "1-command local launcher (./run.sh) designed for client reuse"
        ],
        "demo_tier": tier,
        "live_url": args.live_url.strip(),
        "local_run_cmd": "./run.sh",
        "template": template,
    }

    placeholder_map = {
        "DAY_NUM": str(day),
        "DAY_PADDED": day_padded,
        "SLUG": slug,
        "TITLE": title,
        "CATEGORY": category,
        "CATEGORY_NAME": cat_cfg["name"],
        "DATE": today_iso(),
        "STACK_LIST": ", ".join(stack),
        "UPWORK_NICHE": niche,
        "PROBLEM": problem,
        "SOLUTION": solution,
        "DEMO_TIER": tiers_map[tier]["label"],
        "LOCAL_RUN_CMD": "./run.sh",
        "REPO_URL": repo_cfg["github_url"],
        "PAGES_URL": repo_cfg["pages_url"],
    }

    if args.dry_run:
        print("\n[DRY RUN] Would create:", target_dir)
        print(f"[DRY RUN] Template: templates/{template}")
        print("[DRY RUN] project.json preview:")
        print(json.dumps(project_meta, indent=2))
        return 0

    template_dir = TEMPLATES_DIR / template
    copy_template(template_dir, target_dir, placeholder_map)

    meta_path = target_dir / "project.json"
    meta_path.write_text(json.dumps(project_meta, indent=2) + "\n", encoding="utf-8")

    print(f"\nCreated projects/{folder_name}/ from templates/{template}/")
    print("Next steps:")
    print(f"  1. Build the demo inside projects/{folder_name}/ (keep DEMO_MODE=true working offline).")
    print(f"  2. Test local launch: cd 'projects/{folder_name}' && ./run.sh")
    print(f"  3. Add architecture diagram/screenshots to projects/{folder_name}/assets/.")
    print(f"  4. Set \"status\": \"completed\" and \"date_completed\": \"{today_iso()}\" in project.json.")
    print("  5. Run: python3 scripts/sync.py")
    print(f"  6. Generate proposal blurb anytime: python3 scripts/pitch.py --day {day}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
