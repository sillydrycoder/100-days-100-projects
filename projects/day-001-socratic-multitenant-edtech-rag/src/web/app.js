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

  function renderSources(res) {
    const badge = $("hint-badge");
    badge.classList.remove("hidden");
    badge.textContent = `Hint ${res.hint_level} / 3`;

    const parts = [];
    if (res.vision_structured) {
      parts.push(`
        <div class="cite-item">
          <div class="cite-title">ATTACHED DIAGRAM · ${esc(res.vision_structured.title || "Class Diagram")}</div>
          <div class="cite-excerpt">${esc(res.vision_structured.key_concept || "")}</div>
        </div>
      `);
    }

    if (res.citations.length) {
      res.citations.forEach((c) => {
        parts.push(`
          <div class="cite-item">
            <div class="cite-title">${esc(c.label)}</div>
            <div class="cite-excerpt">${esc(c.excerpt)}</div>
          </div>
        `);
      });
    } else {
      parts.push(`
        <div class="cite-item">
          <div class="cite-title">NO MATCH IN ACTIVE SCHOOL</div>
          <div class="cite-excerpt">No textbook sections in <strong>${esc(res.school_id)}</strong> matched this question, so the tutor refused to guess or pull from other schools.</div>
        </div>
      `);
    }

    $("sources-panel").innerHTML = parts.join("");
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
    diagSelect.innerHTML =
      `<option value="">None (Text Question)</option>` +
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

    $("chunk-count").textContent = `${chunkData.count} sections`;
    $("chunks-list").innerHTML = chunkData.chunks
      .map(
        (c) => `
      <div class="chunk-card">
        <div class="chunk-head">
          <span class="mono" style="font-size:0.71rem;color:#93a4b8;">${esc(c.parent_context)}</span>
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
      .map((s) => `<option value="${esc(s.school_id)}">${esc(s.name)}</option>`)
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
      `Student (${$("student-ref-input").value})${diagramId ? " · Diagram attached" : ""}`,
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
    appendChat("tutor", `AI Tutor · Step ${res.hint_level} of 3`, res.response);
    renderSources(res);
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
      $("hint-badge").classList.add("hidden");
      $("sources-panel").innerHTML = `<p class="muted">Switched to <strong>${esc(state.activeSchoolId)}</strong>. Ask a question to see citations from this school's textbooks.</p>`;
      await refreshActiveSchoolData();
      appendChat("tutor", "Tutor Ready", `Now tutoring inside ${state.activeSchoolId}. All answers are grounded only in this school's textbooks.`);
    });

    $("new-session-btn").addEventListener("click", () => {
      state.sessionId = `sess_${Math.random().toString(36).slice(2, 8)}`;
      $("chat-log").innerHTML = "";
      $("hint-badge").classList.add("hidden");
      appendChat("tutor", "New Chat", "Started a fresh tutoring session. Ask any question from your textbook or attach a diagram below.");
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

    $("preset-concept").addEventListener("click", async () => {
      $("diagram-select").value = "";
      const q = state.activeSchoolId === "sch_crestview"
        ? "How much ATP is produced in cellular respiration?"
        : "How do I calculate acceleration on a frictionless inclined ramp?";
      await sendTurn(q, "");
    });

    $("preset-other-school").addEventListener("click", async () => {
      $("diagram-select").value = "";
      const q = state.activeSchoolId === "sch_oakridge"
        ? "Explain oxidative phosphorylation ATP yield and enzyme denaturation at 37 C."
        : "Calculate the acceleration of a 4 kg block on a 30-degree frictionless incline ramp.";
      await sendTurn(q, "");
    });

    $("import-csv-btn").addEventListener("click", async () => {
      try {
        const res = await api("/api/onboarding/csv", {
          method: "POST",
          body: JSON.stringify({ school_id: state.activeSchoolId, csv_text: $("csv-input").value }),
        });
        $("csv-status").textContent = `Uploaded: +${res.inserted} new, ${res.updated} updated.`;
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
        $("school-status").textContent = `Created '${res.school.name}'!`;
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
        $("ingest-status").textContent = `Added ${res.chunk_count} sections to ${res.school_id}.`;
        await loadSchools(true);
      } catch (err) {
        $("ingest-status").textContent = `Error: ${err.message}`;
      }
    });
  }

  async function init() {
    wireEvents();
    const health = await api("/api/health");
    $("mode-pill").textContent = health.mode === "demo" ? "DEMO_MODE" : "LIVE LLM";
    await loadSchools();
    appendChat(
      "tutor",
      "Tutor Ready",
      "Welcome! Pick an example above or type your own question from your school's textbook. I'll guide you step-by-step instead of giving away the answer."
    );
  }

  document.addEventListener("DOMContentLoaded", init);
})();
