(() => {
  const state = {
    data: null,
    category: "all",
    tier: "all",
    query: "",
  };

  const els = {
    authorName: document.getElementById("author-name"),
    authorHeadline: document.getElementById("author-headline"),
    authorPositioning: document.getElementById("author-positioning"),
    repoLink: document.getElementById("repo-link"),
    profileLink: document.getElementById("profile-link"),
    copyFilterBtn: document.getElementById("copy-filter-btn"),
    progressFraction: document.getElementById("progress-fraction"),
    progressBarWrap: document.getElementById("progress-bar-wrap"),
    progressFill: document.getElementById("progress-fill"),
    nextDayVal: document.getElementById("next-day-val"),
    pillarCountVal: document.getElementById("pillar-count-val"),
    updatedVal: document.getElementById("updated-val"),
    pillarsGrid: document.getElementById("pillars-grid"),
    resetFiltersBtn: document.getElementById("reset-filters-btn"),
    searchInput: document.getElementById("search-input"),
    tierSelect: document.getElementById("tier-select"),
    resultsCounter: document.getElementById("results-counter"),
    projectsGrid: document.getElementById("projects-grid"),
    emptyState: document.getElementById("empty-state"),
    toast: document.getElementById("toast"),
  };

  let toastTimer = null;
  function showToast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove("visible"), 2400);
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function readQueryParams() {
    const params = new URLSearchParams(window.location.search);
    const cat = params.get("category");
    const q = params.get("q");
    const tier = params.get("tier");
    if (cat) state.category = cat;
    if (q) state.query = q;
    if (tier) state.tier = tier;
  }

  function syncUrlParams() {
    const params = new URLSearchParams();
    if (state.category !== "all") params.set("category", state.category);
    if (state.tier !== "all") params.set("tier", state.tier);
    if (state.query.trim()) params.set("q", state.query.trim());
    const qs = params.toString();
    const nextUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
  }

  function copyText(text, successMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        () => showToast(successMsg),
        () => showToast(text)
      );
    } else {
      showToast(text);
    }
  }

  function renderHeader(data) {
    const { repo, stats, generated_at } = data;
    els.authorName.textContent = repo.author;
    els.authorHeadline.textContent = repo.headline;
    els.authorPositioning.textContent = repo.positioning;
    els.repoLink.href = repo.github_url;
    els.profileLink.href = `https://github.com/${repo.handle}`;
    els.profileLink.textContent = `@${repo.handle} Profile`;

    const pct = Math.min(100, Math.max(0, stats.completion_pct || 0));
    els.progressFraction.textContent = `${stats.completed_count} / ${stats.target_total}`;
    els.progressBarWrap.setAttribute("aria-valuenow", String(Math.round(pct)));
    els.progressFill.style.width = `${pct}%`;

    const nextPadded = String(stats.next_day || 1).padStart(3, "0");
    els.nextDayVal.textContent = `DAY ${nextPadded}`;
    els.pillarCountVal.textContent = String((stats.categories || []).length);
    els.updatedVal.textContent = generated_at ? generated_at.slice(0, 10) : "—";
  }

  function renderPillars(data) {
    const categories = data.stats.categories || [];
    const totalDone = data.stats.completed_count || 0;
    const totalTarget = data.stats.target_total || 100;
    const totalPct = totalTarget ? Math.round((totalDone / totalTarget) * 100) : 0;

    const allCard = `
      <button type="button" class="pillar-card ${state.category === "all" ? "active" : ""}" data-category="all" style="--pillar-accent: #10b981;">
        <div class="pillar-top">
          <span class="pillar-title"><span class="pillar-dot" style="background:#10b981;"></span>All Pillars</span>
          <span class="pillar-count mono">${totalDone}/${totalTarget}</span>
        </div>
        <div class="pillar-bar"><div class="pillar-bar-fill" style="width:${totalPct}%; background:#10b981;"></div></div>
        <div class="pillar-skills">Full 100-project catalog</div>
      </button>
    `;

    const cards = categories
      .map((cat) => {
        const isActive = state.category === cat.slug;
        const pct = cat.target ? Math.min(100, Math.round((cat.completed / cat.target) * 100)) : 0;
        const skills = (cat.skills || []).slice(0, 4).join(" · ");
        return `
          <button type="button" class="pillar-card ${isActive ? "active" : ""}" data-category="${escapeHtml(cat.slug)}" style="--pillar-accent: ${escapeHtml(cat.accent)};">
            <div class="pillar-top">
              <span class="pillar-title">
                <span class="pillar-dot" style="background:${escapeHtml(cat.accent)};"></span>
                ${escapeHtml(cat.short_name)}
              </span>
              <span class="pillar-count mono">${cat.completed}/${cat.target}</span>
            </div>
            <div class="pillar-bar">
              <div class="pillar-bar-fill" style="width:${pct}%; background:${escapeHtml(cat.accent)};"></div>
            </div>
            <div class="pillar-skills">${escapeHtml(skills)}</div>
          </button>
        `;
      })
      .join("");

    els.pillarsGrid.innerHTML = allCard + cards;

    els.pillarsGrid.querySelectorAll(".pillar-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.category = btn.getAttribute("data-category") || "all";
        syncUrlParams();
        renderAll();
      });
    });
  }

  function filterProjects(projects, catMap) {
    const q = state.query.trim().toLowerCase();
    return projects.filter((p) => {
      if (state.category !== "all" && p.category !== state.category) return false;
      if (state.tier !== "all" && p.demo_tier !== state.tier) return false;
      if (!q) return true;
      const cat = catMap[p.category] || {};
      const blob = [
        p.title,
        p.slug,
        p.upwork_niche,
        p.problem,
        p.solution,
        ...(p.stack || []),
        ...(p.highlights || []),
        cat.name || "",
        ...(cat.skills || []),
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }

  function renderProjects(data) {
    const catMap = {};
    (data.stats.categories || []).forEach((c) => {
      catMap[c.slug] = c;
    });
    const tiers = data.demo_tiers || {};
    const allProjects = data.projects || [];
    const filtered = filterProjects(allProjects, catMap);

    const hasActiveFilters =
      state.category !== "all" || state.tier !== "all" || Boolean(state.query.trim());
    els.resetFiltersBtn.classList.toggle("hidden", !hasActiveFilters);
    els.resultsCounter.textContent = `${filtered.length} ${filtered.length === 1 ? "demo" : "demos"}`;

    if (filtered.length === 0) {
      els.projectsGrid.innerHTML = "";
      els.emptyState.classList.remove("hidden");

      if (allProjects.length === 0) {
        const selectedCat = state.category !== "all" ? catMap[state.category] : null;
        const heading = selectedCat
          ? `${selectedCat.name} — Queued (${selectedCat.target} planned demos)`
          : "Challenge Initialized — Day 001 Launching Next";
        const body = selectedCat
          ? selectedCat.description
          : "Every day, a real commercial engineering requirement is built into a self-contained, zero-key-runnable demo across these 7 pillars.";

        const roadmapCards = (selectedCat ? [selectedCat] : data.stats.categories || [])
          .map(
            (c) => `
            <div class="roadmap-mini-card">
              <strong style="color:${escapeHtml(c.accent)};">${escapeHtml(c.name)} (${c.target})</strong>
              <span>${escapeHtml(c.description)}</span>
            </div>
          `
          )
          .join("");

        els.emptyState.innerHTML = `
          <h3>${escapeHtml(heading)}</h3>
          <p>${escapeHtml(body)}</p>
          <div class="roadmap-mini">${roadmapCards}</div>
        `;
      } else {
        els.emptyState.innerHTML = `
          <h3>No demos matched your current filter</h3>
          <p>Try clearing your search term or switching to another service pillar.</p>
        `;
      }
      return;
    }

    els.emptyState.classList.add("hidden");

    const cards = filtered
      .slice()
      .reverse()
      .map((p) => {
        const cat = catMap[p.category] || { short_name: p.category, accent: "#10b981" };
        const tierInfo = tiers[p.demo_tier] || { short: "Local" };
        const stackTags = (p.stack || [])
          .map((s) => `<span class="stack-tag">${escapeHtml(s)}</span>`)
          .join("");
        const wipTag =
          p.status !== "completed" ? `<span class="wip-badge mono">WIP</span>` : "";
        const liveBtn = p.live_url
          ? `<a class="btn btn-primary btn-sm" href="${escapeHtml(p.live_url)}" target="_blank" rel="noopener">Live Demo</a>`
          : "";
        const localCmd = `cd ${p.rel_path} && ${p.local_run_cmd || "./run.sh"}`;

        return `
          <article class="project-card">
            <div class="card-meta-row">
              <div style="display:flex; gap:6px; align-items:center;">
                <span class="day-pill mono">DAY ${escapeHtml(p.day_padded)}</span>
                ${wipTag}
              </div>
              <span class="tier-pill mono">${escapeHtml(tierInfo.short)}</span>
            </div>
            <div class="card-pillar">
              <span class="pillar-dot" style="background:${escapeHtml(cat.accent)};"></span>
              <span>${escapeHtml(cat.short_name)}</span>
            </div>
            <h3>${escapeHtml(p.title)}</h3>
            <p class="card-summary">${escapeHtml(p.solution || p.problem)}</p>
            <div class="stack-row">${stackTags}</div>
            <div class="card-actions">
              ${liveBtn}
              <a class="btn btn-secondary btn-sm" href="${escapeHtml(p.readme_url)}" target="_blank" rel="noopener">
                Case Study &amp; Code
              </a>
              <button class="btn btn-ghost btn-sm copy-cmd-btn" type="button" data-cmd="${escapeHtml(localCmd)}">
                Copy Local Run
              </button>
            </div>
          </article>
        `;
      })
      .join("");

    els.projectsGrid.innerHTML = cards;
    els.projectsGrid.querySelectorAll(".copy-cmd-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.getAttribute("data-cmd") || "./run.sh";
        copyText(cmd, "Local run command copied!");
      });
    });
  }

  function renderAll() {
    if (!state.data) return;
    renderHeader(state.data);
    renderPillars(state.data);
    renderProjects(state.data);
  }

  async function init() {
    readQueryParams();
    els.searchInput.value = state.query;
    els.tierSelect.value = state.tier;

    els.searchInput.addEventListener("input", (e) => {
      state.query = e.target.value;
      syncUrlParams();
      renderProjects(state.data);
    });

    els.tierSelect.addEventListener("change", (e) => {
      state.tier = e.target.value;
      syncUrlParams();
      renderProjects(state.data);
    });

    els.resetFiltersBtn.addEventListener("click", () => {
      state.category = "all";
      state.tier = "all";
      state.query = "";
      els.searchInput.value = "";
      els.tierSelect.value = "all";
      syncUrlParams();
      renderAll();
    });

    els.copyFilterBtn.addEventListener("click", () => {
      copyText(window.location.href, "Shareable portfolio link copied!");
    });

    try {
      const res = await fetch("projects.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.data = await res.json();
      // Validate requested category against loaded config
      const validCats = new Set((state.data.stats.categories || []).map((c) => c.slug));
      if (state.category !== "all" && !validCats.has(state.category)) {
        state.category = "all";
      }
      renderAll();
    } catch (err) {
      els.emptyState.classList.remove("hidden");
      els.emptyState.innerHTML = `
        <h3>Unable to load projects.json</h3>
        <p>Run <code>python3 scripts/sync.py</code> and serve <code>docs/</code> via HTTP (e.g. <code>python3 -m http.server --directory docs</code>) or GitHub Pages.</p>
      `;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
