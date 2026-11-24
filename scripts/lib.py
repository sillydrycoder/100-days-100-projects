"""Shared zero-dependency utilities for the 100 Days, 100 Projects command center."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "categories.json"
PROJECTS_DIR = REPO_ROOT / "projects"
TEMPLATES_DIR = REPO_ROOT / "templates"
REGISTRY_PATH = REPO_ROOT / "registry.json"
README_PATH = REPO_ROOT / "README.md"
DOCS_PROJECTS_PATH = REPO_ROOT / "docs" / "projects.json"

VALID_STATUSES = {"in-progress", "completed"}
REQUIRED_FIELDS = (
    "day",
    "slug",
    "title",
    "category",
    "status",
    "upwork_niche",
    "problem",
    "solution",
    "stack",
    "highlights",
    "demo_tier",
    "local_run_cmd",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sanitize_slug(raw: str) -> str:
    slug = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def format_day(day: int) -> str:
    return f"{day:03d}"


def ascii_bar(current: int, target: int, width: int = 12) -> str:
    if target <= 0:
        return "░" * width
    ratio = min(max(current / target, 0.0), 1.0)
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def list_templates() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(
        p.name for p in TEMPLATES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def discover_projects(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Scan projects/day-* directories and return (records, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    records: list[dict[str, Any]] = []

    valid_categories = {c["slug"]: c for c in config["categories"]}
    valid_tiers = set(config["demo_tiers"].keys())
    repo_cfg = config["repo"]
    github_base = repo_cfg["github_url"].rstrip("/")
    branch = repo_cfg.get("branch", "main")

    if not PROJECTS_DIR.exists():
        return records, errors, warnings

    seen_days: dict[int, str] = {}

    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not entry.name.startswith("day-"):
            warnings.append(f"Skipping non-day directory: projects/{entry.name}")
            continue

        meta_path = entry / "project.json"
        if not meta_path.exists():
            errors.append(f"projects/{entry.name}: missing project.json")
            continue

        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            errors.append(f"projects/{entry.name}/project.json: invalid JSON ({exc})")
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in data]
        if missing:
            errors.append(f"projects/{entry.name}/project.json: missing required fields {missing}")
            continue

        day = data.get("day")
        if not isinstance(day, int) or day < 1 or day > 999:
            errors.append(f"projects/{entry.name}/project.json: 'day' must be an integer 1..999")
            continue

        expected_prefix = f"day-{format_day(day)}-"
        if not entry.name.startswith(expected_prefix):
            errors.append(
                f"projects/{entry.name}: folder name should start with '{expected_prefix}' to match day={day}"
            )

        if day in seen_days:
            errors.append(
                f"Duplicate day {day}: found in both '{seen_days[day]}' and 'projects/{entry.name}'"
            )
        seen_days[day] = f"projects/{entry.name}"

        category = data.get("category")
        if category not in valid_categories:
            errors.append(
                f"projects/{entry.name}: unknown category '{category}'. Valid: {sorted(valid_categories)}"
            )

        tier = data.get("demo_tier")
        if tier not in valid_tiers:
            errors.append(
                f"projects/{entry.name}: unknown demo_tier '{tier}'. Valid: {sorted(valid_tiers)}"
            )

        status = data.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"projects/{entry.name}: invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}"
            )

        if not isinstance(data.get("stack"), list) or not data["stack"]:
            errors.append(f"projects/{entry.name}: 'stack' must be a non-empty list")

        if not isinstance(data.get("highlights"), list):
            errors.append(f"projects/{entry.name}: 'highlights' must be a list")

        if not (entry / "README.md").exists():
            errors.append(f"projects/{entry.name}: missing README.md")

        has_runner = (entry / "run.sh").exists() or (entry / "docker-compose.yml").exists()
        if not has_runner:
            warnings.append(
                f"projects/{entry.name}: missing run.sh or docker-compose.yml local runner"
            )

        if status == "in-progress":
            warnings.append(f"Day {format_day(day)} ({data['title']}): still marked 'in-progress'")

        for text_field in ("title", "upwork_niche", "problem", "solution"):
            val = str(data.get(text_field, ""))
            if "TODO" in val.upper():
                warnings.append(
                    f"Day {format_day(day)}: field '{text_field}' still contains TODO placeholder"
                )

        assets_dir = entry / "assets"
        asset_files = (
            sorted(
                f.name
                for f in assets_dir.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
            if assets_dir.exists()
            else []
        )

        rel_path = f"projects/{entry.name}"
        enriched = dict(data)
        enriched["day_padded"] = format_day(day)
        enriched["folder"] = entry.name
        enriched["rel_path"] = rel_path
        enriched["github_url"] = f"{github_base}/tree/{branch}/{rel_path}"
        enriched["readme_url"] = f"{github_base}/blob/{branch}/{rel_path}/README.md"
        enriched["assets"] = asset_files
        enriched["live_url"] = str(data.get("live_url") or "").strip()
        enriched["date_completed"] = str(data.get("date_completed") or "").strip()
        records.append(enriched)

    records.sort(key=lambda item: item["day"])
    return records, errors, warnings


def compute_stats(config: dict[str, Any], projects: list[dict[str, Any]]) -> dict[str, Any]:
    target_total = int(config["repo"].get("target_total", 100))
    completed = [p for p in projects if p["status"] == "completed"]
    in_progress = [p for p in projects if p["status"] == "in-progress"]
    next_day = max((p["day"] for p in projects), default=0) + 1

    by_category: list[dict[str, Any]] = []
    for cat in config["categories"]:
        slug = cat["slug"]
        cat_completed = sum(1 for p in completed if p["category"] == slug)
        cat_in_progress = sum(1 for p in in_progress if p["category"] == slug)
        target = int(cat["target"])
        pct = round((cat_completed / target) * 100, 1) if target > 0 else 0.0
        remaining = max(target - cat_completed, 0)
        by_category.append(
            {
                "slug": slug,
                "name": cat["name"],
                "short_name": cat["short_name"],
                "target": target,
                "completed": cat_completed,
                "in_progress": cat_in_progress,
                "remaining": remaining,
                "pct": pct,
                "accent": cat["accent"],
                "default_template": cat["default_template"],
                "skills": cat["skills"],
                "description": cat["description"],
            }
        )

    # Recommend categories with remaining quota, ordered by lowest % complete then largest target
    recommended = sorted(
        [c for c in by_category if c["remaining"] > 0],
        key=lambda c: (c["pct"], -c["remaining"], -c["target"]),
    )

    last_completed = completed[-1] if completed else None
    return {
        "target_total": target_total,
        "completed_count": len(completed),
        "in_progress_count": len(in_progress),
        "total_tracked": len(projects),
        "completion_pct": round((len(completed) / target_total) * 100, 1) if target_total else 0.0,
        "next_day": next_day,
        "last_completed": (
            {
                "day": last_completed["day"],
                "day_padded": last_completed["day_padded"],
                "title": last_completed["title"],
                "category": last_completed["category"],
                "date_completed": last_completed["date_completed"],
            }
            if last_completed
            else None
        ),
        "categories": by_category,
        "recommended_next_categories": [c["slug"] for c in recommended[:3]],
    }
