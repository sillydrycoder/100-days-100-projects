# AGENTS.md — Operating Manual for AI Coding Assistants

> **Purpose:** This file is the canonical contract for Antigravity or any future AI assistant collaborating on **Muhammad Ali's (`sillydrycoder`) 100 Days, 100 Projects — Freelance Proof-of-Work Engine**. Read this file and `registry.json` before making changes.

---

## 1. Mission & Brand Standard

- **Owner:** Muhammad Ali (`sillydrycoder`)
- **Upwork Positioning:** `AI Automation & Full-Stack Engineer | Python, LangGraph, RAG, Laravel`
- **Brand Promise:** *"Reliable backend architecture instead of fragile prototypes."*
- **Objective:** Build **100 real-world, client-grade reference demos** inspired by daily Upwork job posts so every project serves simultaneously as:
  1. Verifiable proof-of-work for GitHub and Upwork proposals.
  2. A portfolio piece matching Muhammad's dark-mode architecture-diagram aesthetic.
  3. A clean, forkable starter repository when a paid client contract arrives.

**Never build childish/toy tutorials** (calculators, tic-tac-toe, generic to-do apps). Every build must solve a genuine commercial engineering problem.

---

## 2. Mandatory Startup Protocol (Every Session)

Before scaffolding or writing code for a new project:
1. Run `python3 scripts/sync.py --status` to inspect:
   - The current completion count (`X / 100`) and next available Day number (`day-XXX`).
   - Category coverage gaps across the 7 service pillars defined in `config/categories.json`.
   - Any `in-progress` projects that should be finished before starting a new day.
2. If the user provides an Upwork job description:
   - **Anonymize strictly:** Strip client names, company names, domains, contact details, private repos, proprietary documents, and budget details.
   - **Scope a crisp 1-day vertical slice:** Focus on the highest-signal architectural core (e.g., stateful LangGraph workflow + citation retrieval, idempotent Stripe webhook + token ledger, multi-tenant RBAC API, or resilient Playwright ETL pipeline).
   - **Pick the matching pillar** from `config/categories.json` and the right starter template from `templates/`.

---

## 3. Repository Architecture & Longevity Invariants

This repository is designed to remain **100% functional 10+ years from now**:

1. **Zero external dependencies for root tooling:** `scripts/lib.py`, `scripts/new_day.py`, `scripts/sync.py`, and `scripts/pitch.py` MUST use **Python 3 standard library only**.
2. **Zero build pipeline for the Showcase Hub:** `docs/` (`index.html`, `styles.css`, `app.js`, `projects.json`) MUST remain pure static HTML/CSS/vanilla JS served directly by GitHub Pages from `main` → `/docs`.
3. **Never hand-edit generated files:**
   - Root `README.md`, `registry.json`, and `docs/projects.json` are generated exclusively by `python3 scripts/sync.py`.
   - Source of truth for project data is each folder's `projects/day-XXX-<slug>/project.json`.
4. **Public professionalism:** NEVER store Upwork sales scripts or "how to win bids" text inside `projects/day-XXX-<slug>/`. Public project folders must read purely as senior engineering case studies. Proposal snippets are generated on demand via `python3 scripts/pitch.py`.

---

## 4. Per-Project Engineering Quality Bar

Every folder `projects/day-XXX-<slug>/` MUST contain:

| File / Folder | Requirement |
| :--- | :--- |
| `project.json` | Valid metadata matching the schema below. |
| `README.md` | Client-ready Case Study: Overview, Business Problem, Architecture (Mermaid diagram), Key Capabilities, Live Demo (if hosted) OR 1-Command Local Quick Start, Production Reliability Notes, and Tech Stack. |
| `run.sh` | Executable (`chmod +x`) 1-command local runner (or paired with `docker-compose.yml`). |
| `.env.example` | Complete documented environment variables with safe defaults (`DEMO_MODE=true`). |
| `sample_data/` | Realistic, fully anonymized fixtures (JSON, CSV, HTML, SQLite seed) so demos work offline forever. |
| `assets/` | Architecture diagram SVG/PNG and/or UI screenshots / demo GIF when applicable. |
| `src/` (or framework root) | Clean, modular, readable implementation with pinned dependencies and at least one smoke test or verification command. |

### Mandatory `DEMO_MODE=true` Rule
Whenever a project uses paid external APIs (OpenAI, Anthropic, Gemini, Stripe, third-party SaaS APIs, or live scraping targets that may change HTML over time):
- Default to `DEMO_MODE=true` when API keys are omitted so anyone cloning the repo can execute `./run.sh` and witness the full end-to-end workflow immediately with zero cost and zero broken external dependencies.
- Keep real provider integration cleanly wired behind environment variables so switching `DEMO_MODE=false` with real keys works seamlessly.

---

## 5. `project.json` Schema Reference

Every `projects/day-XXX-<slug>/project.json` must validate against `scripts/sync.py`:

```json
{
  "day": 1,
  "slug": "support-triage-rag",
  "title": "Multi-Agent Support Triage & Citation RAG",
  "category": "ai-agents-rag",
  "status": "completed",
  "date_completed": "2026-11-24",
  "upwork_niche": "AI customer support automation with grounded knowledge retrieval",
  "problem": "Support teams lose hours triaging repetitive tickets while generic chatbots hallucinate policies.",
  "solution": "Built a stateful LangGraph triage & hybrid RAG pipeline that classifies tickets, retrieves cited policy snippets, and escalates low-confidence cases.",
  "stack": ["Python", "LangGraph", "FastAPI", "SQLite"],
  "highlights": [
    "Stateful LangGraph routing with confidence-based human escalation",
    "Deterministic offline DEMO_MODE + drop-in OpenAI/Gemini provider switch",
    "Structured JSON audit log and automated smoke tests"
  ],
  "demo_tier": "tier-2-free-app",
  "live_url": "",
  "local_run_cmd": "./run.sh",
  "template": "python-ai-rag"
}
```

Valid `category` values are defined in `config/categories.json`.
Valid `demo_tier` values: `tier-1-static`, `tier-2-free-app`, `tier-3-local-visual`.
Valid `status` values: `in-progress`, `completed`.

---

## 6. Mandatory Finish Protocol (Before Completing Any Day)

Before reporting a Day as finished:
1. Run the project's local `./run.sh` (or automated smoke test) and verify it succeeds cleanly in `DEMO_MODE=true`.
2. Ensure zero secrets, `.env` files, or client-identifying information exist anywhere in the diff.
3. Update `projects/day-XXX-<slug>/project.json` (`"status": "completed"`, `"date_completed": "YYYY-MM-DD"`, accurate `"problem"`, `"solution"`, `"highlights"`, and `"live_url"` if deployed).
4. Run `python3 scripts/sync.py --check` and `python3 scripts/sync.py` so `registry.json`, `README.md`, and `docs/projects.json` are 100% up to date.
5. Run `python3 scripts/pitch.py --day <N>` and include the generated proposal blurb in your handoff message to Muhammad.
