# START HERE — The 10-Year Resume Guide

> **Opened this repository after weeks, months, or 10 years away?**
> You do not need to remember anything. Every rule, progress metric, template, and automation script lives inside this folder with **zero external dependencies** (plain Python 3 + JSON + static HTML/JS).

---

## 1. Resume in 60 Seconds

Run this command from the repository root:

```bash
python3 scripts/sync.py --status
```

It instantly tells you:
1. How many projects are complete (`X / 100`) and what **Day Number** is next.
2. Which of your **7 Upwork service pillars** have the biggest coverage gaps (so you know what kind of job to pick next).
3. Whether any project has missing fields or is still marked `in-progress`.

If you are working with an AI coding assistant (Antigravity, Claude, Codex, or any future agent), just say:

> *"Read `AGENTS.md` and `registry.json`, run `python3 scripts/sync.py --status`, and let's start the next day based on this Upwork job post: [paste job post]."*

---

## 2. The Daily Upwork-to-Demo Routine

1. **Browse Upwork** for a real job in one of your underrepresented pillars (shown by `sync.py --status`).
2. **Anonymize & Scope a 1-Day Vertical Slice:**
   - Remove all client names, company names, private URLs, emails, and proprietary files.
   - Scope the core **20% architecture slice** that proves 100% of your engineering competence (e.g., the LangGraph agent loop + RAG retrieval, or the idempotent Stripe token-billing webhook handler, or the multi-tenant Laravel dashboard).
3. **Scaffold the Day Folder (5 seconds):**
   ```bash
   # Interactive mode (prompts you for every field — nothing to memorize):
   python3 scripts/new_day.py

   # Or direct CLI mode:
   python3 scripts/new_day.py \
     --category ai-agents-rag \
     --slug support-triage-rag \
     --title "Multi-Agent Support Triage & Citation RAG" \
     --stack "Python,LangGraph,FastAPI,SQLite"
   ```
4. **Build Clean, Forkable Engineering Proof:**
   - Keep `DEMO_MODE=true` working out of the box with **zero API keys** (mock LLM / mock Stripe / local mock HTML fixtures in `sample_data/`).
   - Ensure `./run.sh` starts the demo in one command locally.
   - Add a **dark-mode Mermaid architecture diagram** in `README.md` and screenshots or a 30–60s GIF in `assets/`.
   - When finished, flip `"status": "completed"` in `projects/day-XXX-<slug>/project.json` (and add `"live_url"` if you deployed it to a free host).
5. **Sync & Publish:**
   ```bash
   python3 scripts/sync.py
   git add .
   git commit -m "feat(day-001): add multi-agent support triage RAG demo"
   git push
   ```
   `scripts/sync.py` automatically validates your project, updates `registry.json`, regenerates the master `README.md` catalog, and updates `docs/projects.json` for your free GitHub Pages Portfolio Hub.

---

## 3. Free-First Hosting Rules (Zero Monthly Cost)

Never pay for demo servers or waste hours wrestling with fragile infrastructure:

| Tier | Best For | Free Host | Required Permanent Fallback |
| :--- | :--- | :--- | :--- |
| **`tier-1-static`** | Interactive web UIs, dashboards, simulators, Flutter Web | **GitHub Pages** (`docs/demos/day-XXX/`) or **Vercel / Cloudflare Pages** | `./run.sh` + screenshots in `assets/` |
| **`tier-2-free-app`** | LangGraph/RAG demos, ML/Data apps, lightweight FastAPI/Streamlit | **Hugging Face Spaces** or **Streamlit Community Cloud** | `./run.sh` + `DEMO_MODE=true` + screenshots/GIF |
| **`tier-3-local-visual`** | Laravel stacks, Stripe webhook backends, Playwright/Puppeteer bots | **Local only** (no flaky free tier!) | `./run.sh` (or `docker compose up`) + Architecture Diagram + screenshots/GIF in `README.md` |

---

## 4. Using Past Demos to Win Upwork Jobs

Whenever a relevant Upwork job appears — tomorrow or 5 years from now — search your catalog locally:

```bash
# Search by skill, keyword, or domain:
python3 scripts/pitch.py --search "langgraph"
python3 scripts/pitch.py --search "stripe"

# Filter by service pillar:
python3 scripts/pitch.py --category laravel-saas-backend

# Generate a ready-to-paste proposal block for a specific day:
python3 scripts/pitch.py --day 1 --format full

# Grab just the live links & filtered Portfolio Hub URL:
python3 scripts/pitch.py --category ai-agents-rag --format links
```

### Reusing a Demo as a Paid Client Starter Kit
Because every project folder under `projects/day-XXX-<slug>/` is completely self-contained, when you win a real contract:
1. Copy `projects/day-XXX-<slug>/` into a brand-new private client repository.
2. Swap `DEMO_MODE=false`, plug in the client's real keys in `.env`, and customize business logic on top of the working architecture.

---

## 5. One-Time GitHub & Free GitHub Pages Setup

If you have not pushed this repo to GitHub yet:

```bash
# 1. Create an empty public repo named `100-days-100-projects` at https://github.com/new
# 2. Link and push:
git remote add origin https://github.com/sillydrycoder/100-days-100-projects.git
git push -u origin main
```

Then enable your free **Portfolio Showcase Hub** (takes 10 seconds):
1. Open `https://github.com/sillydrycoder/100-days-100-projects/settings/pages`
2. Under **Build and deployment → Source**, select **Deploy from a branch**
3. Select Branch **`main`**, Folder **`/docs`**, and click **Save**
4. Your live, searchable, category-filterable portfolio hub goes live at:
   `https://sillydrycoder.github.io/100-days-100-projects/`

You can send clients pre-filtered portfolio links directly in proposals, e.g.:
- `https://sillydrycoder.github.io/100-days-100-projects/?category=ai-agents-rag`
- `https://sillydrycoder.github.io/100-days-100-projects/?category=stripe-api-integrations`
- `https://sillydrycoder.github.io/100-days-100-projects/?category=laravel-saas-backend`
