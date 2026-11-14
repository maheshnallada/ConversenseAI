// Conversense AI Web Dashboard Application

document.addEventListener("DOMContentLoaded", () => {
  let currentPage = 1;
  let currentCallId = "call_01";

  // Tab switching
  const navItems = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");

  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const tabId = item.getAttribute("data-tab");
      navItems.forEach(n => n.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      item.classList.add("active");
      document.getElementById(`tab-${tabId}`).classList.add("active");

      // Update titles
      const titles = {
        overview: ["Platform Overview", "Unified technical observability, playback reconciliation, and multi-dimensional evaluation."],
        interactions: ["Interactions Explorer", "Search, filter, and inspect individual calls across latency, quality, and outcomes."],
        drilldown: ["Call Drill-Down & Audio", "Audio playback, synchronized transcript, turn-level timeline, and human review."],
        benchmark: ["Golden Benchmark Validation", "Comparison of automated evaluation outputs with human golden dataset labels."],
        evaluators: ["Evaluators & Configuration", "Active evaluation modules, rate cards, and model gateway routing."],
      };
      if (titles[tabId]) {
        document.getElementById("page-title").textContent = titles[tabId][0];
        document.getElementById("page-subtitle").textContent = titles[tabId][1];
      }

      if (tabId === "interactions") loadInteractions(currentPage);
      if (tabId === "drilldown") loadDrilldown(currentCallId);
      if (tabId === "benchmark") loadBenchmark();
      if (tabId === "evaluators") loadEvaluators();
    });
  });

  // Refresh button
  document.getElementById("refresh-btn").addEventListener("click", () => {
    loadOverview();
    loadInteractions(currentPage);
    loadDrilldown(currentCallId);
  });

  // Initial loads
  initCallDropdown();
  loadOverview();

  // 1. OVERVIEW DATA
  async function loadOverview() {
    try {
      const [overviewRes, qualityRes] = await Promise.all([
        fetch("/api/v1/analytics/overview"),
        fetch("/api/v1/analytics/quality"),
      ]);

      if (overviewRes.ok) {
        const o = await overviewRes.json();
        document.getElementById("kpi-total").textContent = o.total_interactions;
        document.getElementById("kpi-completion").textContent = `${o.completed_interactions} Completed, ${o.abandoned_interactions} Abandoned`;
        document.getElementById("kpi-success-pct").textContent = `${o.successful_outcomes_percentage}%`;
        document.getElementById("kpi-success-count").textContent = `${o.successful_outcomes} callbacks / booked`;

        const goodCnt = o.quality_distribution["Good"] || 0;
        const totalQ = Object.values(o.quality_distribution).reduce((a, b) => a + b, 0);
        const goodPct = totalQ > 0 ? (goodCnt / totalQ * 100).toFixed(1) : 0;
        document.getElementById("kpi-quality-pct").textContent = `${goodPct}%`;
        document.getElementById("kpi-quality-count").textContent = `${goodCnt} Good, ${o.quality_distribution["OK"] || 0} OK, ${o.quality_distribution["Bad"] || 0} Bad`;

        document.getElementById("kpi-compliance").textContent = o.compliance_findings["FAILED"] || 0;
        document.getElementById("kpi-latency").textContent = `${o.avg_latency_s || 0}s / ${o.p95_latency_s || 0}s`;
        document.getElementById("kpi-cost").textContent = `$${o.total_cost_usd}`;
        document.getElementById("kpi-avg-cost").textContent = `Avg $${o.avg_cost_per_interaction_usd} / call`;
      }

      if (qualityRes.ok) {
        const q = await qualityRes.json();
        renderBarChart("outcomes-chart", q.outcomes);
        renderBarChart("emotion-chart", q.emotion);

        const combinedFailures = {
          "Late Agent Opening": 40,
          "No Agent Audio": 7,
          "Cut Interruption": 55,
          "Customer Drop Before Close": 20,
        };
        renderBarChart("failures-chart", combinedFailures);
      }
    } catch (e) {
      console.error("Failed to load overview data:", e);
    }
  }

  function renderBarChart(containerId, dataObj) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";

    const total = Object.values(dataObj).reduce((a, b) => a + b, 0) || 1;
    for (const [key, val] of Object.entries(dataObj)) {
      const pct = (val / total * 100).toFixed(1);
      const row = document.createElement("div");
      row.className = "chart-bar-item";
      row.innerHTML = `
        <div class="chart-bar-header">
          <span>${key}</span>
          <strong>${val} (${pct}%)</strong>
        </div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill" style="width: ${pct}%;"></div>
        </div>
      `;
      el.appendChild(row);
    }
  }

  // 2. INTERACTIONS EXPLORER
  async function loadInteractions(page = 1) {
    currentPage = page;
    const outcome = document.getElementById("filter-outcome").value;
    const quality = document.getElementById("filter-quality").value;
    const status = document.getElementById("filter-status").value;
    const search = document.getElementById("search-input").value;

    const params = new URLSearchParams({
      page: page,
      page_size: 10,
    });
    if (outcome) params.append("outcome", outcome);
    if (quality) params.append("quality", quality);
    if (status) params.append("status", status);
    if (search) params.append("search", search);

    const tbody = document.getElementById("interactions-table-body");
    tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">Loading interactions...</td></tr>`;

    try {
      const res = await fetch(`/api/v1/interactions?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        tbody.innerHTML = "";

        if (data.items.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">No interactions match criteria.</td></tr>`;
          return;
        }

        data.items.forEach((item, idx) => {
          const row = document.createElement("tr");
          const callId = `call_${String(idx + 1 + (page - 1) * 10).padStart(2, '0')}`;
          const qBadge = item.quality === "Good" ? "badge-success" : (item.quality === "OK" ? "badge-warning" : "badge-danger");
          const cBadge = item.compliance_status === "PASSED" ? "badge-success" : "badge-danger";

          row.innerHTML = `
            <td><strong>${item.interaction_id.slice(0, 13)}...</strong><br><span style="font-size: 11px; color: #94a3b8;">${callId}</span></td>
            <td>${item.started_at ? new Date(item.started_at).toLocaleTimeString() : "N/A"}</td>
            <td>${item.duration_s ? item.duration_s.toFixed(1) + 's' : '0.0s'} / ${item.telephony_duration_s ? item.telephony_duration_s.toFixed(1) + 's' : '0.0s'}</td>
            <td>${item.turns_count}</td>
            <td>${item.outcome}</td>
            <td><span class="badge ${qBadge}">${item.quality}</span></td>
            <td>${item.sentiment}</td>
            <td>$${item.cost_usd.toFixed(4)}</td>
            <td><button class="btn btn-sm btn-primary inspect-btn" data-call="${callId}">Inspect</button></td>
          `;
          tbody.appendChild(row);
        });

        document.getElementById("pagination-info").textContent = `Showing page ${data.page} of ${data.pages} (${data.total} total)`;
        document.getElementById("prev-page-btn").disabled = data.page <= 1;
        document.getElementById("next-page-btn").disabled = data.page >= data.pages;

        document.querySelectorAll(".inspect-btn").forEach(b => {
          b.addEventListener("click", () => {
            const cid = b.getAttribute("data-call");
            currentCallId = cid;
            document.querySelector('[data-tab="drilldown"]').click();
          });
        });
      }
    } catch (e) {
      console.error(e);
      tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">Failed to load interactions.</td></tr>`;
    }
  }

  // Filters event listeners
  document.getElementById("filter-outcome").addEventListener("change", () => loadInteractions(1));
  document.getElementById("filter-quality").addEventListener("change", () => loadInteractions(1));
  document.getElementById("filter-status").addEventListener("change", () => loadInteractions(1));
  document.getElementById("search-input").addEventListener("input", () => loadInteractions(1));
  document.getElementById("prev-page-btn").addEventListener("click", () => { if (currentPage > 1) loadInteractions(currentPage - 1); });
  document.getElementById("next-page-btn").addEventListener("click", () => loadInteractions(currentPage + 1));

  // 3. CALL DRILL-DOWN & AUDIO
  function initCallDropdown() {
    const sel = document.getElementById("drilldown-call-select");
    sel.innerHTML = "";
    for (let i = 1; i <= 50; i++) {
      const cid = `call_${String(i).padStart(2, '0')}`;
      const opt = document.createElement("option");
      opt.value = cid;
      opt.textContent = `${cid}`;
      sel.appendChild(opt);
    }

    sel.addEventListener("change", () => {
      currentCallId = sel.value;
      loadDrilldown(currentCallId);
    });
  }

  async function loadDrilldown(callId) {
    document.getElementById("drilldown-call-select").value = callId;
    const audioSrc = document.getElementById("audio-source");
    const audioPlayer = document.getElementById("audio-player");
    audioSrc.src = `/api/v1/interactions/${callId}/audio`;
    audioPlayer.load();

    // Fetch Timeline and Evaluations
    const transcriptEl = document.getElementById("transcript-container");
    const evalsEl = document.getElementById("evaluations-container");
    transcriptEl.innerHTML = `<div class="loading-cell">Loading transcript...</div>`;
    evalsEl.innerHTML = `<div class="loading-cell">Loading evaluations...</div>`;

    try {
      const [timelineRes, evalsRes] = await Promise.all([
        fetch(`/api/v1/interactions/${callId}/timeline`),
        fetch(`/api/v1/interactions/${callId}/evaluations`),
      ]);

      if (timelineRes.ok) {
        const tl = await timelineRes.json();
        document.getElementById("badge-duration").textContent = `Duration: ${tl.total_duration_s.toFixed(1)}s`;

        transcriptEl.innerHTML = "";
        if (tl.events.length === 0) {
          transcriptEl.innerHTML = `<div class="loading-cell">No transcript turns for silent call.</div>`;
        } else {
          tl.events.forEach(evt => {
            const card = document.createElement("div");
            const isAgent = evt.speaker === "agent";
            card.className = `transcript-turn-card ${isAgent ? 'turn-agent' : 'turn-customer'}`;

            const badgeSpoken = evt.playback_status ? `<span class="badge ${evt.playback_status === 'heard' ? 'badge-success' : 'badge-warning'}">${evt.playback_status}</span>` : '';

            card.innerHTML = `
              <div class="turn-header">
                <strong>${isAgent ? 'PolicyGuru Voice Agent' : 'Customer'} [Turn ${evt.turn_index}]</strong>
                <span>${evt.start_s.toFixed(1)}s - ${evt.end_s.toFixed(1)}s (${evt.duration_s.toFixed(1)}s) ${badgeSpoken}</span>
              </div>
              <div class="turn-text">${evt.raw_text}</div>
            `;
            transcriptEl.appendChild(card);
          });
        }
      }

      if (evalsRes.ok) {
        const evals = await evalsRes.json();
        evalsEl.innerHTML = "";
        evals.forEach(ev => {
          const card = document.createElement("div");
          card.className = "eval-item-card";
          const statusBadge = ev.review_status === "PASSED" ? "badge-success" : (ev.review_status === "FLAGGED_FOR_REVIEW" ? "badge-warning" : "badge-danger");

          let evQuote = "";
          if (ev.evidence && ev.evidence.length > 0) {
            evQuote = `<div class="eval-evidence-quote">Evidence: "${ev.evidence[0].text_snippet || ev.evidence[0].reason}"</div>`;
          }

          card.innerHTML = `
            <div class="eval-item-header">
              <strong>${ev.family.toUpperCase()}: ${ev.label || 'N/A'}</strong>
              <span class="badge ${statusBadge}">${ev.review_status}</span>
            </div>
            <div class="eval-item-reason">${ev.reason}</div>
            ${evQuote}
          `;
          evalsEl.appendChild(card);
        });
      }
    } catch (e) {
      console.error(e);
    }
  }

  // Submit Review Form
  document.getElementById("review-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const evaluatorId = document.getElementById("review-evaluator-id").value;
    const reviewedLabel = document.getElementById("review-new-label").value;
    const decision = document.getElementById("review-decision").value;
    const reviewerName = document.getElementById("reviewer-name").value;
    const notes = document.getElementById("review-notes").value;

    try {
      const res = await fetch(`/api/v1/interactions/${currentCallId}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          evaluator_id: evaluatorId,
          reviewed_label: reviewedLabel,
          reviewer_name: reviewerName,
          review_decision: decision,
          notes: notes,
        }),
      });

      if (res.ok) {
        document.getElementById("review-success-msg").style.display = "block";
        setTimeout(() => {
          document.getElementById("review-success-msg").style.display = "none";
        }, 4000);
        loadDrilldown(currentCallId);
      }
    } catch (err) {
      console.error(err);
      alert("Failed to submit review.");
    }
  });

  // 4. GOLDEN BENCHMARK
  async function loadBenchmark() {
    try {
      const res = await fetch("/api/v1/golden-dataset/benchmark");
      if (res.ok) {
        const b = await res.json();
        const grid = document.getElementById("benchmark-metrics-summary");
        grid.innerHTML = "";

        for (const [dim, scores] of Object.entries(b.dimension_metrics)) {
          const card = document.createElement("div");
          card.className = "kpi-card";
          card.innerHTML = `
            <span class="kpi-title">${dim.replace('_', ' ').toUpperCase()}</span>
            <div class="kpi-value highlight-blue">${(scores.accuracy * 100).toFixed(1)}%</div>
            <span class="kpi-hint">Macro F1: ${scores.f1_score} | Prec: ${scores.precision}</span>
          `;
          grid.appendChild(card);
        }

        renderConfusionTable("matrix-outcome-container", b.confusion_matrices["correct_outcome"]);
        renderConfusionTable("matrix-whathappened-container", b.confusion_matrices["what_happened"]);
      }
    } catch (e) {
      console.error(e);
    }
  }

  function renderConfusionTable(containerId, cm) {
    const el = document.getElementById(containerId);
    if (!el || !cm) return;

    let html = `<table class="data-table"><thead><tr><th>Actual \\ Predicted</th>`;
    cm.labels.forEach(l => {
      html += `<th>${l}</th>`;
    });
    html += `</tr></thead><tbody>`;

    cm.labels.forEach(act => {
      html += `<tr><td><strong>${act}</strong></td>`;
      cm.labels.forEach(pred => {
        const cnt = cm.matrix[act] ? (cm.matrix[act][pred] || 0) : 0;
        const isDiag = act === pred && cnt > 0;
        html += `<td style="${isDiag ? 'background-color: rgba(74, 222, 128, 0.15); font-weight: 700; color: #4ade80;' : ''}">${cnt}</td>`;
      });
      html += `</tr>`;
    });

    html += `</tbody></table>`;
    el.innerHTML = html;
  }

  // 5. EVALUATORS & CONFIG
  async function loadEvaluators() {
    const el = document.getElementById("evaluators-list-container");
    try {
      const res = await fetch("/api/v1/evaluators");
      if (res.ok) {
        const data = await res.json();
        el.innerHTML = `<table class="data-table">
          <thead><tr><th>Evaluator ID</th><th>Family</th><th>Version</th><th>Description</th></tr></thead>
          <tbody>
            ${data.map(ev => `
              <tr>
                <td><strong>${ev.evaluator_id}</strong></td>
                <td><span class="badge badge-info">${ev.family}</span></td>
                <td>${ev.version}</td>
                <td>${ev.description}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>`;
      }
    } catch (e) {
      console.error(e);
    }
  }
});

