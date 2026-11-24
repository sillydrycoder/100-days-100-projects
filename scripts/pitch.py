#!/usr/bin/env python3
"""Local Upwork proposal helper: search completed demos and format clean proof-of-work snippets.

Keeps public project folders clean and professional while giving you instant proposal links locally.
Zero external dependencies (Python 3 standard library only).

Examples:
    python3 scripts/pitch.py --search "langgraph"
    python3 scripts/pitch.py --category stripe-api-integrations
    python3 scripts/pitch.py --day 1 --format full
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from lib import discover_projects, format_day, load_config


def score_project(project: dict[str, Any], cat_map: dict[str, dict[str, Any]], tokens: list[str]) -> int:
    cat = cat_map.get(project["category"], {})
    haystacks = [
        (project.get("title", ""), 6),
        (" ".join(project.get("stack", [])), 5),
        (project.get("upwork_niche", ""), 4),
        (cat.get("name", ""), 3),
        (" ".join(cat.get("skills", [])), 3),
        (project.get("problem", ""), 2),
        (project.get("solution", ""), 2),
        (" ".join(project.get("highlights", [])), 2),
        (project.get("slug", ""), 4),
    ]
    score = 0
    for token in tokens:
        for text, weight in haystacks:
            if token in text.lower():
                score += weight
    return score


def format_links_line(project: dict[str, Any]) -> str:
    parts = [f"Case Study & Code: {project['github_url']}"]
    if project.get("live_url"):
        parts.insert(0, f"Live Demo: {project['live_url']}")
    return " | ".join(parts)


def render_short(projects: list[dict[str, Any]], filtered_hub_url: str | None) -> str:
    lines = ["Here are relevant production demos I've built that closely match your requirements:", ""]
    for p in projects:
        stack = ", ".join(p["stack"][:5])
        lines.append(f"- **{p['title']}** ({stack}): {p['solution']}")
        lines.append(f"  {format_links_line(p)}")
    if filtered_hub_url:
        lines.extend(["", f"Browse more demos in this track: {filtered_hub_url}"])
    return "\n".join(lines)


def render_full(projects: list[dict[str, Any]], filtered_hub_url: str | None) -> str:
    blocks: list[str] = []
    for p in projects:
        stack = ", ".join(p["stack"])
        highlights = "\n".join(f"  • {h}" for h in p.get("highlights", [])[:3])
        block = [
            f"### Day {p['day_padded']}: {p['title']}",
            f"Problem addressed: {p['problem']}",
            f"What I engineered: {p['solution']}",
            f"Stack: {stack}",
        ]
        if highlights:
            block.append("Key engineering details:")
            block.append(highlights)
        block.append(format_links_line(p))
        blocks.append("\n".join(block))
    if filtered_hub_url:
        blocks.append(f"Full filtered showcase: {filtered_hub_url}")
    return "\n\n".join(blocks)


def render_links(projects: list[dict[str, Any]], filtered_hub_url: str | None) -> str:
    lines = [
        f"Day {p['day_padded']} — {p['title']}: {format_links_line(p)}"
        for p in projects
    ]
    if filtered_hub_url:
        lines.append(f"Filtered Portfolio Hub: {filtered_hub_url}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search past demos and generate Upwork proposal proof snippets.")
    parser.add_argument("--day", type=int, help="Select a specific day number")
    parser.add_argument("--category", help="Filter by service pillar slug")
    parser.add_argument("--search", help="Keyword search across title, stack, niche, problem, and solution")
    parser.add_argument("--top", type=int, default=3, help="Maximum matching demos to display (default: 3)")
    parser.add_argument(
        "--format",
        choices=("short", "full", "links"),
        default="short",
        help="Output style (default: short)",
    )
    parser.add_argument(
        "--include-in-progress",
        action="store_true",
        help="Include projects still marked in-progress",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    cat_map = {c["slug"]: c for c in config["categories"]}
    pages_url = config["repo"]["pages_url"]
    projects, _, _ = discover_projects(config)

    if not args.include_in_progress:
        projects = [p for p in projects if p["status"] == "completed"]

    if args.category:
        if args.category not in cat_map:
            print(f"Error: Unknown category '{args.category}'. Valid: {', '.join(cat_map)}", file=sys.stderr)
            return 1
        projects = [p for p in projects if p["category"] == args.category]

    if args.day is not None:
        projects = [p for p in projects if p["day"] == args.day]
        if not projects:
            print(
                f"No matching project found for Day {format_day(args.day)} "
                "(try adding --include-in-progress if it is not completed yet).",
                file=sys.stderr,
            )
            return 1

    if args.search:
        tokens = [t for t in re.split(r"[\s,/+]+", args.search.lower()) if t]
        scored = [(score_project(p, cat_map, tokens), p) for p in projects]
        scored = [(s, p) for s, p in scored if s > 0]
        scored.sort(key=lambda pair: (-pair[0], -pair[1]["day"]))
        projects = [p for _, p in scored]
    else:
        projects = list(reversed(projects))

    if not projects:
        hub_hint = f"{pages_url}?category={args.category}" if args.category else pages_url
        print("No completed demos matched your filter yet.")
        print(f"Portfolio Hub URL: {hub_hint}")
        return 0

    selected = projects[: max(args.top, 1)]
    filtered_hub_url = None
    if args.category:
        filtered_hub_url = f"{pages_url}?category={args.category}"
    elif len({p["category"] for p in selected}) == 1:
        filtered_hub_url = f"{pages_url}?category={selected[0]['category']}"

    if args.format == "short":
        print(render_short(selected, filtered_hub_url))
    elif args.format == "full":
        print(render_full(selected, filtered_hub_url))
    else:
        print(render_links(selected, filtered_hub_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
