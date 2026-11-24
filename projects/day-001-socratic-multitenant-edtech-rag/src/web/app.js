(() => {
  const state = {
    schools: [],
    activeSchoolId: "",
    sessionId: `sess_${Math.random().toString(36).slice(2, 8)}`,
  };

  const $ = (id) => document.getElementById(id);

  function esc(val) {
    return String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function appendChat(role, meta, text) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = `<div class="msg-meta">${esc(meta)}</div><div>${esc(text)}</div>`;
    const log = $("chat-log");
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function renderTelemetry(res) {
    const r = res.routing;
    const tierClass = r.vision_cache_hit ? "tier-hit" : r.tier === "vision-vlm" ? "tier-vlm" : "";
    const piiBadge = res.pii_redacted
      ? `STRIPPED (${res.pii_types.join(", ")})`
      : "Clean (Pseudonymized)";

    const citationsHtml = res.citations.length
      ? res.citations
          .map(
            (c) => `
          <div class="cite-item">
            <div class="mono" style="color:#6ee7b7;font-size:0.74rem;">${esc(c.label)} · RRF ${c.rrf_score}</div>
            <div class="muted" style="font-size:0.78rem;margin-top:3px;">${esc(c.excerpt)}</div>
          </div>`
          )
          .join("")
      : `<div class="cite-item muted">0 chunks matched inside tenant <code>${esc(res.school_id)}</code> (strict isolation prevented out-of-school retrieval).</div>`;

    const traceHtml = res.graph_trace
      .map(
        (t) => `
      <div class="trace-item">
        <div class="trace-top"><span>${esc(t.node)}</span><span>${t.elapsed_ms} ms</span></div>
        <div class="trace-detail">${esc(t.detail)}</div>
      </div>`
      )
      .join("");

    $("telemetry-panel").innerHTML = `
      <div class="kv-grid">
        <div class="kv-box">
          <span>MODEL TIER ROUTED</span>
          <strong class="mono ${tierClass}">${esc(r.tier)}</strong>
        </div>
        <div class="kv-box">
          <span>EST. TURN COST</span>
          <strong class="mono">$${r.est_cost_usd.toFixed(5)}${r.vision_savings_pct ? ` (-${r.vision_savings_pct}%)` : ""}</strong>
        </div>
        <div class="kv-box">
          <span>SOCRATIC STATE</span>
          <strong class="mono">Attempt #${res.attempt_number} · Hint ${res.hint_level}/3</strong>
        </div>
        <div class="kv-box">
          <span>FERPA/COPPA PII GUARD</span>
          <strong class="mono">${esc(piiBadge)}</strong>
        </div>
      </div>
      <div class="kv-box">
        <span>PROMPT SENT TO MODEL (POST-REDACTION)</span>
        <div class="mono" style="font-size:0.76rem;color:#cbd5e1;margin-top:3px;">${esc(res.redacted_query)}</div>
      </div>
      <div>
        <h3 class="subhead" style="margin-top:4px;">Grounded Tenant Citations (${res.citations.length})</h3>
        ${citationsHtml}
      </div>
      <div>
        <h3 class="subhead" style="margin-top:4px;">7-Node Stateful Execution Trace</h3>
        <div class="trace-list">${traceHtml}</div>
      </div>
    `;
  }

  async function refreshActiveSchoolData() {
    const sid = state.activeSchoolId;
    if (!sid) return;

    const [diagData, userData, chunkData] = await Promise.all([
      api(`/api/diagrams?school_id=${encodeURIComponent(sid)}`),
      api(`/api/users?school_id=${encodeURIComponent(sid)}`),
      api(`/api/chunks?school_id=${encodeURIComponent(sid)}`),
    ]);

    const diagSelect = $("diagram-select");
    diagSelect.innerHTML = `<option value="">None (Text-Only Query)</option>` +
      diagData.diagrams
        .map((d) => `<option value="${esc(d.diagram_id)}">${esc(d.title)}</option>`)
        .join("");

    $("roster-count").textContent = `${userData.users.length} users`;
    $("roster-tbody").innerHTML = userData.users
      .map(
        (u) => `
      <tr>
        <td class="mono">${esc(u.external_id)}</td>
        <td class="mono">${esc(u.role)}</td>
        <td>${esc(u.grade_level)} · ${esc(u.class_section)}</td>
        <td>${esc(u.display_name)}</td>
        <td class="mono">${esc(u.email)}</td>
      </tr>`
      )
      .join("");

    const firstStudent = userData.users.find((u) => u.role === "student");
    if (firstStudent) $("student-ref-input").value = firstStudent.external_id;

    $("chunk-count").textContent = `${chunkData.count} chunks`;
    $("chunks-list").innerHTML = chunkData.chunks
      .map(
        (c) => `
      <div class="chunk-card">
        <div class="chunk-head">
          <span class="mono" style="font-size:0.73rem;color:#93a4b8;">${esc(c.parent_context)}</span>
          <span class="btype btype-${esc(c.block_type)} mono">${esc(c.block_type)}</span>
        </div>
        <pre class="chunk-body">${esc(c.content)}</pre>
      </div>`
      )
      .join("");
  }

  async function loadSchools(keepSelected = false) {
    const data = await api("/api/schools");
    state.schools = data.schools;
    const sel = $("school-select");
    sel.innerHTML = state.schools
      .map((s) => `<option value="${esc(s.school_id)}">${esc(s.name)} (${s.chunk_count} chunks)</option>`)
      .join("");
    if (keepSelected && state.schools.some((s) => s.school_id === state.activeSchoolId)) {
      sel.value = state.activeSchoolId;
    } else if (state.schools.length) {
      state.activeSchoolId = state.schools[0].school_id;
      sel.value = state.activeSchoolId;
    }
    await refreshActiveSchoolData();
  }

  async function sendTurn(query, diagramId = "") {
    appendChat(
      "student",
      `${state.activeSchoolId} · ${$("student-ref-input").value}${diagramId ? ` · +Diagram(${diagramId})` : ""}`,
      query
    );
    const res = await api("/api/tutor/chat", {
      method: "POST",
      body: JSON.stringify({
        school_id: state.activeSchoolId,
        session_id: state.sessionId,
        student_ref: $("student-ref-input").value,
        query,
        diagram_id: diagramId || null,
      }),
    });
    appendChat(
      "tutor",
      `Socratic Tutor · Hint ${res.hint_level}/3 · ${res.routing.tier} ($${res.routing.est_cost_usd.toFixed(5)})`,
      res.response
    );
    renderTelemetry(res);
  }

  async function refreshCostEstimate() {
    const students = $("sl-students").value;
    const schools = $("sl-schools").value;
    const days = $("sl-days").value;
    const vision = $("sl-vision").value;
    const cache = $("sl-cache").value;

    $("val-students").textContent = Number(students).toLocaleString();
    $("val-schools").textContent = schools;
    $("val-days").textContent = `${days} active / ${365 - Number(days)} idle`;
    $("val-vision").textContent = `${vision}%`;
    $("val-cache").textContent = `${cache}%`;

    const res = await api(
      `/api/cost/estimate?students=${students}&schools=${schools}&active_days=${days}&vision_pct=${vision}&cache_pct=${cache}`
    );

    $("cost-results").innerHTML = `
      <div class="cost-card warn">
        <span class="mono muted">DEDICATED 24/7 GPU CLUSTER</span>
        <div class="cost-big" style="color:#fda4af;">$${res.dedicated_24_7.annual_total_usd.toLocaleString()}/yr</div>
        <ul class="cost-list">
          <li>Provisioned GPUs for peak hours: <strong>${res.dedicated_24_7.gpus_provisioned}x L40S/A100</strong></li>
          <li><strong>Wasted spend during ${res.inputs.idle_days} vacation days:</strong> $${res.dedicated_24_7.idle_vacation_waste_usd.toLocaleString()}/yr</li>
          <li>Avg monthly burn (even in summer): $${res.dedicated_24_7.avg_monthly_usd.toLocaleString()}/mo</li>
        </ul>
      </div>
      <div class="cost-card highlight">
        <span class="mono" style="color:#10b981;">SERVERLESS SCALE-TO-ZERO + ROUTING</span>
        <div class="cost-big" style="color:#6ee7b7;">$${res.serverless_scale_to_zero.annual_total_usd.toLocaleString()}/yr</div>
        <ul class="cost-list">
          <li>Annual Inference (Tiered + Cache): <strong>$${res.serverless_scale_to_zero.inference_annual_usd.toLocaleString()}</strong></li>
          <li>Vacation-month infra cost: <strong>$${res.serverless_scale_to_zero.vacation_monthly_usd.toLocaleString()}/mo</strong> (near-zero idle!)</li>
          <li>Unit economics: <strong>$${res.serverless_scale_to_zero.cost_per_student_year_usd}/student/year</strong></li>
        </ul>
      </div>
      <div class="cost-card">
        <span class="mono muted">NET ARCHITECTURE SAVINGS</span>
        <div class="cost-big" style="color:#93c5fd;">${res.savings.annual_pct}% Saved</div>
        <ul class="cost-list">
          <li>Annual savings vs 24/7 GPUs: <strong>$${res.savings.annual_usd.toLocaleString()}/yr</strong></li>
          <li>Saved via Vision-to-JSON Cache alone: <strong>$${res.savings.vision_cache_annual_savings_usd.toLocaleString()}/yr</strong></li>
          <li>Annual student turns handled: <strong>${res.volume.annual_turns.toLocaleString()}</strong></li>
        </ul>
      </div>
    `;
  }

  function wireEvents() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $(`tab-${btn.dataset.tab}`).classList.add("active");
      });
    });

    $("school-select").addEventListener("change", async (e) => {
      state.activeSchoolId = e.target.value;
      state.sessionId = `sess_${Math.random().toString(36).slice(2, 8)}`;
      $("chat-log").innerHTML = "";
      await refreshActiveSchoolData();
      appendChat("tutor", "System", `Switched RLS TenantContext to '${state.activeSchoolId}'. Only this school's textbooks and roster are accessible.`);
    });

    $("new-session-btn").addEventListener("click", () => {
      state.sessionId = `sess_${Math.random().toString(36).slice(2, 8)}`;
      $("chat-log").innerHTML = "";
      appendChat("tutor", "System", `Started fresh Socratic session (${state.sessionId}) — Hint progression reset to 1/3.`);
    });

    $("chat-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = $("query-input").value.trim();
      if (!q) return;
      const diag = $("diagram-select").value;
      $("query-input").value = "";
      await sendTurn(q, diag);
    });

    $("preset-diagram").addEventListener("click", async () => {
      const diagOpt = $("diagram-select").options[1];
      const diagId = diagOpt ? diagOpt.value : "";
      if (diagId) $("diagram-select").value = diagId;
      const q = state.activeSchoolId === "sch_crestview"
        ? "Why does the enzyme reaction rate drop so steeply after 37 C on this graph?"
        : "How do I find the total displacement from this velocity-time graph?";
      await sendTurn(q, diagId);
    });

    $("preset-pii").addEventListener("click", async () => {
      const q = "Hi, I'm Aiden Brooks (STU-201, a.brooks@oakridge.example.edu, 555-234-9810). Can you help me understand acceleration on a frictionless ramp?";
      await sendTurn(q, "");
    });

    $("preset-isolation").addEventListener("click", async () => {
      const crossQ = state.activeSchoolId === "sch_oakridge"
        ? "Explain oxidative phosphorylation ATP yield and enzyme denaturation at 37 C."
        : "Calculate the acceleration of a 4 kg block on a 30-degree frictionless incline ramp.";
      await sendTurn(crossQ, "");
    });

    $("import-csv-btn").addEventListener("click", async () => {
      try {
        const res = await api("/api/onboarding/csv", {
          method: "POST",
          body: JSON.stringify({ school_id: state.activeSchoolId, csv_text: $("csv-input").value }),
        });
        $("csv-status").textContent = `Imported: +${res.inserted} new, ${res.updated} updated, ${res.errors.length} errors.`;
        await loadSchools(true);
      } catch (err) {
        $("csv-status").textContent = `Error: ${err.message}`;
      }
    });

    $("school-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/schools", {
          method: "POST",
          body: JSON.stringify({
            school_id: $("new-school-id").value,
            name: $("new-school-name").value,
            curriculum: $("new-school-curr").value,
          }),
        });
        $("school-status").textContent = `Created tenant '${res.school.school_id}'!`;
        state.activeSchoolId = res.school.school_id;
        await loadSchools(true);
      } catch (err) {
        $("school-status").textContent = `Error: ${err.message}`;
      }
    });

    $("ingest-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/ingest/textbook", {
          method: "POST",
          body: JSON.stringify({
            school_id: state.activeSchoolId,
            title: $("book-title").value,
            subject: $("book-subject").value,
            grade_level: $("book-grade").value,
            content: $("book-content").value,
          }),
        });
        $("ingest-status").textContent = `Indexed ${res.chunk_count} atomic chunks (${JSON.stringify(res.counts_by_type)}) into ${res.school_id}.`;
        await loadSchools(true);
      } catch (err) {
        $("ingest-status").textContent = `Error: ${err.message}`;
      }
    });

    ["sl-students", "sl-schools", "sl-days", "sl-vision", "sl-cache"].forEach((id) => {
      $(id).addEventListener("input", refreshCostEstimate);
    });
  }

  async function init() {
    wireEvents();
    const health = await api("/api/health");
    $("mode-pill").textContent = health.mode === "demo" ? "DEMO_MODE (OFFLINE)" : "LIVE LLM MODE";
    const rls = await api("/api/schema/rls");
    $("rls-sql-box").textContent = rls.sql;
    await loadSchools();
    await refreshCostEstimate();
    appendChat(
      "tutor",
      "Ready",
      "Welcome! Pick a Quick Test chip above or ask a textbook question. Try clicking 'Diagram + Vision Cache' twice to watch Turn 1 invoke Vision VLM and Turn 2 hit the tenant Vision Cache (saving 92.6% inference cost)."
    );
  }

  document.addEventListener("DOMContentLoaded", init);
})();
