"use strict";

const ROLES = {
  coordinator: { name: "Sarah Kim, RN", title: "Study Coordinator", initials: "SK", nav: ["intake", "inbox", "registry", "signed"], defaultView: "intake", canSign: false, canManagePatients: true },
  pi: { name: "Dr. Vance, MD", title: "Principal Investigator", initials: "DV", nav: ["inbox", "registry", "signed"], defaultView: "inbox", canSign: true, canManagePatients: false },
  monitor: { name: "J. Alvarez", title: "Clinical Monitor (CRA)", initials: "JA", nav: ["inbox", "registry", "signed"], defaultView: "inbox", canSign: false, canManagePatients: false },
  patient: { name: "PT-004 (You)", title: "Study Subject", initials: "P4", nav: ["submit", "myreports"], defaultView: "submit", canSign: false, canManagePatients: false },
};

const PATIENT_ID = "PT-004";

const state = {
  pending: [], stats: {}, selectedId: null, signer: "PI-DR-VANCE-MD", showingLock: false,
  role: localStorage.getItem("careclaw_role") || "coordinator",
  intake: { noteName: null, noteText: null, labsName: null, labsJson: null },
};

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function sevClass(sev) {
  const s = String(sev || "").toUpperCase();
  if (s === "CRITICAL") return "critical";
  if (s === "HIGH") return "high";
  return "major";
}
function sevChip(sev) {
  const s = String(sev || "MAJOR").toUpperCase();
  if (s === "CRITICAL") return "crit";
  return "major";
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

let toastTimer;
function toast(msg, isErr) {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 2600);
}

/* ---------------- data ---------------- */
function queueSig(pending, stats) {
  return pending.map((c) => c.case_id).join(",") + "#" + (stats.pending ?? 0) + "#" + (stats.signed ?? 0);
}

async function loadQueue(keepSelection, skipDetail, poll) {
  const data = await api("/api/queue");
  const pending = data.pending || [];
  const stats = data.stats || {};
  const sig = queueSig(pending, stats);
  // On a background poll, do nothing if the queue is unchanged — no flicker, no re-render.
  if (poll && sig === state.lastSig) return;
  state.lastSig = sig;
  state.pending = pending;
  state.stats = stats;
  state.signer = data.signer || state.signer;
  if (!keepSelection || !state.pending.some((c) => c.case_id === state.selectedId)) {
    state.selectedId = state.pending.length ? state.pending[0].case_id : null;
  }
  renderKpis();
  renderList();
  if (!skipDetail) renderDetail();
  $("#navPending").textContent = state.stats.pending ?? 0;
  $("#navSigned").textContent = state.stats.signed ?? 0;
  $("#listCount").textContent = state.pending.length;
}

/* ---------------- KPIs ---------------- */
function renderKpis() {
  const s = state.stats;
  const tiles = [
    { ico: "📥", cls: "p", val: s.pending ?? 0, lbl: "Cases awaiting review" },
    { ico: "⚠️", cls: "a", val: s.deviations ?? 0, lbl: "Protocol deviations flagged" },
    { ico: "🔴", cls: "c", val: s.critical ?? 0, lbl: "Critical severity alerts" },
    { ico: "🔒", cls: "g", val: s.signed ?? 0, lbl: "Signed & Part 11 locked" },
  ];
  $("#kpis").innerHTML = tiles
    .map(
      (t) => `<div class="kpi"><div class="kpi-ico ${t.cls}">${t.ico}</div>
        <div><div class="kpi-val">${t.val}</div><div class="kpi-lbl">${esc(t.lbl)}</div></div></div>`
    )
    .join("");
}

/* ---------------- case list ---------------- */
function renderList() {
  const el = $("#caseList");
  if (!state.pending.length) {
    el.innerHTML = `<div class="empty-note">Queue is empty.<br>Drop PT-004 fixtures to enqueue a case.</div>`;
    return;
  }
  el.innerHTML = state.pending
    .map((c) => {
      const meta = c.patient_meta || {};
      const devs = c.deviations || [];
      const hasCrit = devs.some((d) => String(d.severity).toUpperCase() === "CRITICAL");
      const hasSevereLab = (c.lab_findings || []).some((l) => l.is_severe);
      const chips = [];
      if (hasCrit) chips.push(`<span class="chip crit">● CRITICAL</span>`);
      if (devs.length) chips.push(`<span class="chip major">${devs.length} deviation${devs.length > 1 ? "s" : ""}</span>`);
      if (hasSevereLab) chips.push(`<span class="chip grade">Grade 3 lab</span>`);
      if (!chips.length) chips.push(`<span class="chip ok">Clear</span>`);
      return `<button class="case-card ${c.case_id === state.selectedId ? "active" : ""}" data-id="${esc(c.case_id)}" type="button">
        <div class="cc-top"><span class="cc-pid">${esc(meta.patient_id || "?")}</span>
          <span class="cc-day">Study Day ${esc(meta.study_day ?? "?")}</span></div>
        <div class="cc-mid">${esc(meta.protocol_id || "")} · ${esc(meta.age || "?")}${esc((meta.sex || "")[0] || "")}
          <span class="phase-chip">${esc(meta.phase || "Phase 1")}</span></div>
        <div class="cc-chips">${chips.join("")}</div>
      </button>`;
    })
    .join("");
  el.querySelectorAll(".case-card").forEach((b) =>
    b.addEventListener("click", () => {
      state.selectedId = b.dataset.id;
      renderList();
      renderDetail();
    })
  );
}

/* ---------------- detail ---------------- */
function labTrend(finding, raw) {
  // pull baseline from raw lab_data if available
  const chem = (raw && raw.chemistry) || {};
  const key = finding.analyte.split(" ")[0].replace(/[^A-Za-z]/g, "");
  const map = { ALT: "ALT", AST: "AST", Total: "Total_Bilirubin" };
  const entry = chem[map[key]] || chem[key];
  if (entry && entry.baseline_value != null) return `${entry.baseline_value} → <span class="up">▲</span>`;
  return "—";
}

function renderDetail() {
  const el = $("#detail");
  state.showingLock = false;
  const c = state.pending.find((x) => x.case_id === state.selectedId);
  if (!c) {
    el.innerHTML = `<div class="detail-empty"><div class="de-ico">🗂️</div>
      <h3>No case selected</h3><p>Select a case from the queue, or drop new records into <code>incoming_records/</code>.</p></div>`;
    return;
  }
  const meta = c.patient_meta || {};
  const devs = c.deviations || [];
  const labs = c.lab_findings || [];
  const symptoms = c.symptoms_mapped || [];

  const devHtml = devs.length
    ? devs
        .map((d) => {
          const cls = sevClass(d.severity);
          const drug = d.detected_drug ? `: ${esc(d.detected_drug)}` : "";
          const impact = d.clinical_impact ? `<div class="dev-detail" style="margin-top:6px"><em>${esc(d.clinical_impact)}</em></div>` : "";
          return `<div class="dev ${cls}">
            <div class="dev-ico">${cls === "critical" ? "🔴" : "🟠"}</div>
            <div class="dev-body">
              <div class="dev-title">${esc(d.category)}${drug}
                <span class="chip ${sevChip(d.severity)}">${esc(d.severity || "MAJOR")}</span></div>
              <div class="dev-cite">${esc(d.protocol_section || "Protocol rule")}</div>
              <div class="dev-detail">${esc(d.details || "")}</div>
              ${impact}
              ${d.action_required ? `<div class="dev-action"><b>Action:</b><span>${esc(d.action_required)}</span></div>` : ""}
            </div></div>`;
        })
        .join("")
    : `<div class="no-dev">✓ No protocol deviations detected.</div>`;

  const labRows = labs
    .map((l) => {
      const severe = l.is_severe ? "severe" : "";
      return `<tr class="${severe}">
        <td class="an">${esc(l.analyte)}</td>
        <td class="num">${esc(l.value)}</td>
        <td class="num">${esc(l.uln_multiple)}</td>
        <td>${l.is_severe ? `<span class="chip grade">${esc(l.ctcae_grade)}</span>` : `<span class="chip mut">${esc(l.ctcae_grade)}</span>`}</td>
        <td class="trend">${labTrend(l, c.lab_data)}</td>
      </tr>`;
    })
    .join("");

  const meddra = [
    ...symptoms.map((s) => ({ pt: s.meddra_pt, code: s.meddra_code })),
    ...labs.map((l) => ({ pt: l.meddra_pt, code: l.meddra_code })),
  ];
  const seen = new Set();
  const meddraHtml = meddra
    .filter((m) => m.pt && !seen.has(m.code) && seen.add(m.code))
    .map((m) => `<span class="md-chip">${esc(m.pt)}<code>${esc(m.code)}</code></span>`)
    .join("");

  el.innerHTML = `
    <div class="card">
      <div class="phead">
        <div>
          <div class="p-id">${esc(meta.patient_id || "?")} <span class="phase-chip">${esc(meta.phase || "Phase 1")}</span></div>
          <div class="cc-day" style="margin-top:2px">${esc(meta.age || "?")} yrs · ${esc(meta.sex || "?")}</div>
        </div>
        <div class="p-meta">
          <div class="pm"><span class="k">Study Day</span><span class="v">${esc(meta.study_day ?? "?")}</span></div>
          <div class="pm"><span class="k">Protocol</span><span class="v">${esc(meta.protocol_id || "")}</span></div>
          <div class="pm"><span class="k">Note date</span><span class="v">${esc(meta.note_date || "")}</span></div>
          <div class="pm"><span class="k">Source</span><span class="v">${esc((c.source_files || []).length)} file(s)</span></div>
        </div>
        <span class="status-pill">● ${esc((c.status || "NEEDS_PI_REVIEW").replace(/_/g, " "))}</span>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><span class="ch-badge proto">🚨</span>
        <div><h2>ProtocolClaw — Deviation Sentinel</h2><div class="ch-sub">Deterministic audit vs protocol rules</div></div>
        <span class="ch-right chip ${devs.length ? "major" : "ok"}">${devs.length} finding${devs.length === 1 ? "" : "s"}</span>
      </div>
      <div class="card-body">${devHtml}</div>
    </div>

    <div class="card">
      <div class="card-h"><span class="ch-badge safety">📋</span>
        <div><h2>SafetyClaw — FDA 3500A Scribe</h2><div class="ch-sub">CTCAE v5.0 grading · MedDRA v27.0</div></div>
      </div>
      <div class="card-body">
        ${labs.length
          ? `<table class="labs"><thead><tr><th>Analyte</th><th>Value</th><th>ULN</th><th>CTCAE grade</th><th>Baseline</th></tr></thead><tbody>${labRows}</tbody></table>`
          : `<div class="no-dev" style="color:var(--text-2);background:var(--surface-2)">No lab toxicities graded.</div>`}
        ${meddraHtml ? `<div class="meddra">${meddraHtml}</div>` : ""}
      </div>
    </div>

    <div class="card">
      <div class="card-h" id="narrHead" style="cursor:pointer">
        <span class="ch-badge safety">📄</span>
        <div><h2>Pre-drafted FDA 3500A / CIOMS I narrative</h2><div class="ch-sub">Zero-draft for PI adjudication</div></div>
        <span class="ch-right nt-hint" id="narrHint">Hide ▲</span>
      </div>
      <div class="card-body" id="narrBody">
        <pre class="narrative">${esc(c.draft_narrative || "(no narrative)")}</pre>
        <div class="causality-note">⚖️ Causality &amp; action fields remain <b style="margin:0 3px">blank</b> — CareClaw never decides causality. The PI does.</div>
        ${ROLES[state.role].canSign
          ? `<button class="btn ghost" id="openChatBtn" type="button" style="margin-top:12px">💬 Open in chat — iterate on this draft</button>`
          : ""}
      </div>
    </div>

    ${ROLES[state.role].canSign
      ? `<div class="actionbar">
          <button class="btn primary" id="signBtn" type="button">🔒 Approve Deviation &amp; Sign 3500A</button>
          <button class="btn danger" id="dismissBtn" type="button">Dismiss</button>
          <div class="ab-note">Signs as <b>${esc(state.signer)}</b> and writes a SHA-256 21 CFR Part 11 lock locally.</div>
        </div>`
      : `<div class="actionbar"><div class="ab-note" style="margin:0;max-width:none;text-align:left">👁 Review-only for the <b>${esc(ROLES[state.role].title)}</b>. Electronic sign-off requires the <b>Principal Investigator</b> role.</div></div>`
    }`;

  // narrative collapse
  const nh = $("#narrHead"), nb = $("#narrBody"), hint = $("#narrHint");
  nh.addEventListener("click", () => {
    const hidden = nb.hasAttribute("hidden");
    if (hidden) { nb.removeAttribute("hidden"); hint.textContent = "Hide ▲"; }
    else { nb.setAttribute("hidden", ""); hint.textContent = "Show ▼"; }
  });

  const signBtn = $("#signBtn"), dismissBtn = $("#dismissBtn");
  if (signBtn) signBtn.addEventListener("click", () => signCase(c.case_id));
  if (dismissBtn) dismissBtn.addEventListener("click", () => dismissCase(c.case_id));
  const openChatBtn = $("#openChatBtn");
  if (openChatBtn) openChatBtn.addEventListener("click", () => openWorkspace(c.case_id));
}

/* ---------------- actions ---------------- */
async function signCase(caseId) {
  const btn = $("#signBtn");
  btn.disabled = true; btn.textContent = "Signing…";
  try {
    const { audit } = await api(`/api/sign/${encodeURIComponent(caseId)}`, { method: "POST" });
    toast("Electronic record signed & locked ✓");
    // refresh stats + list, but keep the lock confirmation in the detail pane
    await loadQueue(false, true);
    state.selectedId = null;
    renderList();
    showLock(audit);
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false; btn.textContent = "🔒 Approve Deviation & Sign 3500A";
  }
}

function showLock(audit) {
  state.showingLock = true;
  const el = $("#detail");
  el.innerHTML = `
    <div class="lock">
      <div class="lock-h">🔒 Electronic Record Signed &amp; Locked</div>
      <div class="lock-grid">
        <span class="k">Status</span><span class="v status">${esc(audit.status)}</span>
        <span class="k">Audit ID</span><span class="v">${esc(audit.audit_id)}</span>
        <span class="k">Signer</span><span class="v">${esc(audit.clinician_id)}</span>
        <span class="k">Timestamp</span><span class="v">${esc(audit.timestamp_utc)}</span>
        <span class="k">Standard</span><span class="v">${esc(audit.regulatory_standard)}</span>
        <span class="k">SHA-256</span><div class="lock-hash">${esc(audit.sha256_signature)}</div>
      </div>
    </div>
    <div class="detail-empty"><div class="de-ico">✓</div><h3>Case cleared from queue</h3>
      <p>The signed record is stored in <code>MongoDB · careclaw.events</code>. Select another case to continue.</p></div>`;
}

async function dismissCase(caseId) {
  try {
    await api(`/api/dismiss/${encodeURIComponent(caseId)}`, { method: "POST" });
    toast("Case dismissed from queue");
    await loadQueue(false);
  } catch (e) {
    toast(e.message, true);
  }
}

/* ---------------- signed view ---------------- */
async function loadSigned() {
  const { signed } = await api("/api/signed");
  const el = $("#signedList");
  if (!signed.length) {
    el.innerHTML = `<div class="empty-note">No signed records yet. Approve a case to write a Part 11 lock.</div>`;
    return;
  }
  el.innerHTML = signed
    .map((e) => {
      const a = e.audit_record || {};
      const meta = e.patient_meta || {};
      return `<div class="signed-row">
        <div><div class="sr-id">${esc(a.audit_id || e.case_id)}</div>
          <div class="sr-meta">${esc(meta.patient_id || "")} · Study Day ${esc(meta.study_day ?? "?")} · ${esc(a.clinician_id || state.signer)} · ${esc(a.timestamp_utc || "")}</div></div>
        <span class="sr-status">🔒 ${esc(a.status || "LOCKED")}</span>
        <div class="sr-hash">${esc(a.sha256_signature || "—")}</div>
      </div>`;
    })
    .join("");
}

/* ---------------- patient portal (study subject) ---------------- */
const patientState = { form: null };

async function loadPatientForm() {
  if (patientState.form) { renderPatientForm(patientState.form); return; }
  try {
    const spec = await api("/api/patient/form");
    patientState.form = spec;
    renderPatientForm(spec);
  } catch (e) {
    $("#eformSub").textContent = "Could not load the form: " + e.message;
  }
}

function renderPatientForm(spec) {
  $("#eformTitle").textContent = spec.title || "Daily Study eDiary";
  $("#eformSub").textContent = spec.subtitle || "";
  $("#eformRationale").textContent = spec.rationale || "";

  $("#eformVitals").innerHTML = (spec.vitals || [])
    .map((v) => {
      const range = Array.isArray(v.normal_range) ? `Normal ${v.normal_range[0]}–${v.normal_range[1]} ${esc(v.unit)}` : "";
      return `<label class="eform-field">
        <span class="ef-label">${esc(v.label)} <span class="ef-unit">${esc(v.unit || "")}</span></span>
        <input class="ef-input" type="number" step="${esc(v.step ?? "any")}" data-vital="${esc(v.key)}" placeholder="${esc(v.placeholder || "")}" inputmode="decimal">
        <span class="ef-range">${esc(range)}</span>
      </label>`;
    })
    .join("");

  const sevOpts = (spec.severity_options || ["mild", "moderate", "severe"])
    .map((o) => `<option value="${esc(o)}">${esc(o)}</option>`)
    .join("");
  $("#eformSymptoms").innerHTML = (spec.symptoms || [])
    .map(
      (s) => `<div class="eform-symptom" data-symptom="${esc(s.key)}">
        <label class="ef-check">
          <input type="checkbox" data-sym-check="${esc(s.key)}">
          <span>${esc(s.label)}</span>
        </label>
        <select class="ef-sev" data-sym-sev="${esc(s.key)}" disabled>
          <option value="">severity…</option>${sevOpts}
        </select>
      </div>`
    )
    .join("");
  // enable severity select only when the symptom is checked
  $("#eformSymptoms").querySelectorAll("[data-sym-check]").forEach((cb) =>
    cb.addEventListener("change", () => {
      const sel = $(`[data-sym-sev="${cb.dataset.symCheck}"]`);
      sel.disabled = !cb.checked;
      if (!cb.checked) sel.value = "";
    })
  );

  $("#eformFreeText").innerHTML = (spec.free_text || [])
    .map(
      (f) => `<label class="eform-field eform-textarea">
        <span class="ef-label">${esc(f.label)}</span>
        <textarea class="ef-input" data-text="${esc(f.key)}" rows="${esc(f.rows || 3)}" placeholder="${esc(f.placeholder || "")}"></textarea>
      </label>`
    )
    .join("");
}

function collectReport() {
  const vitals = {};
  document.querySelectorAll("[data-vital]").forEach((i) => {
    if (i.value !== "") vitals[i.dataset.vital] = Number(i.value);
  });
  const symptoms = [];
  document.querySelectorAll("[data-sym-check]").forEach((cb) => {
    if (cb.checked) {
      const sev = $(`[data-sym-sev="${cb.dataset.symCheck}"]`).value || null;
      symptoms.push({ key: cb.dataset.symCheck, present: true, severity: sev });
    }
  });
  const texts = {};
  document.querySelectorAll("[data-text]").forEach((t) => { texts[t.dataset.text] = t.value || null; });
  return { patient_id: PATIENT_ID, vitals, symptoms, meds: texts.meds || null, observations: texts.observations || null };
}

function clearReport() {
  document.querySelectorAll("[data-vital]").forEach((i) => (i.value = ""));
  document.querySelectorAll("[data-sym-check]").forEach((cb) => (cb.checked = false));
  document.querySelectorAll("[data-sym-sev]").forEach((s) => { s.value = ""; s.disabled = true; });
  document.querySelectorAll("[data-text]").forEach((t) => (t.value = ""));
  $("#submitDone").hidden = true; $("#submitDone").innerHTML = "";
}

async function submitReport(ev) {
  ev.preventDefault();
  const btn = $("#submitReportBtn");
  const payload = collectReport();
  if (!Object.keys(payload.vitals).length && !payload.symptoms.length && !payload.meds && !payload.observations) {
    toast("Please enter at least one vital or symptom", true);
    return;
  }
  btn.disabled = true; btn.textContent = "Submitting…";
  try {
    const res = await api("/api/patient/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const done = $("#submitDone");
    done.hidden = false;
    if (res.alert_event_published) {
      const flags = (res.triage.flags || []).map((f) => esc(f.rule)).join(", ");
      done.innerHTML = `<div class="submit-flagged">
        <div class="sf-h">✓ Thank you — your entry was received</div>
        <div class="sf-sub">Your care team has been notified about: <b>${flags}</b>. Someone from your study site may reach out. This is not a diagnosis.</div>
      </div>`;
    } else {
      done.innerHTML = `<div class="submit-ok">
        <div class="so-h">✓ Thank you — your entry was received</div>
        <div class="so-sub">Nothing in today's entry needs urgent attention. Please keep up your daily eDiary.</div>
      </div>`;
    }
    clearReportFields();
    toast("eDiary entry submitted ✓");
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "▶ Submit to care team";
  }
}

// clear inputs but keep the confirmation message visible
function clearReportFields() {
  document.querySelectorAll("[data-vital]").forEach((i) => (i.value = ""));
  document.querySelectorAll("[data-sym-check]").forEach((cb) => (cb.checked = false));
  document.querySelectorAll("[data-sym-sev]").forEach((s) => { s.value = ""; s.disabled = true; });
  document.querySelectorAll("[data-text]").forEach((t) => (t.value = ""));
}

function vitalsSummary(vitals) {
  const spec = patientState.form;
  const units = {};
  if (spec) (spec.vitals || []).forEach((v) => (units[v.key] = v.unit));
  const bits = [];
  if (vitals.temperature_c != null) bits.push(`${vitals.temperature_c}°C`);
  if (vitals.heart_rate_bpm != null) bits.push(`${vitals.heart_rate_bpm} bpm`);
  if (vitals.systolic_bp != null && vitals.diastolic_bp != null) bits.push(`${vitals.systolic_bp}/${vitals.diastolic_bp} mmHg`);
  if (vitals.spo2_pct != null) bits.push(`SpO₂ ${vitals.spo2_pct}%`);
  if (vitals.weight_kg != null) bits.push(`${vitals.weight_kg} kg`);
  return bits.join(" · ") || "—";
}

async function loadMyReports() {
  const el = $("#myReportsList");
  el.innerHTML = `<div class="empty-note">Loading…</div>`;
  try {
    const { reports } = await api(`/api/patient/reports?patient_id=${encodeURIComponent(PATIENT_ID)}`);
    $("#navReports").textContent = reports.length;
    if (!reports.length) {
      el.innerHTML = `<div class="empty-note">No eDiary entries yet.<br>Use “Submit Report” to record today's vitals.</div>`;
      return;
    }
    el.innerHTML = reports
      .map((r) => {
        const t = r.triage || {};
        const notified = t.concern;
        const chip = notified
          ? `<span class="chip crit">⚠ Care team notified</span>`
          : `<span class="chip ok">Received</span>`;
        const syms = (r.symptoms || []).filter((s) => s.present).map((s) => esc(s.key.replace(/_/g, " ")) + (s.severity ? ` (${esc(s.severity)})` : "")).join(", ");
        const when = (r.submitted_at || "").replace("T", " ").slice(0, 16) + " UTC";
        return `<div class="report-row">
          <div class="rr-top">
            <span class="rr-date">${esc(when)}</span>
            ${chip}
          </div>
          <div class="rr-vitals">${esc(vitalsSummary(r.vitals || {}))}</div>
          ${syms ? `<div class="rr-syms">Symptoms: ${syms}</div>` : ""}
          ${notified && r.concern_summary ? `<div class="rr-note">${esc(r.concern_summary)}</div>` : ""}
        </div>`;
      })
      .join("");
  } catch (e) {
    el.innerHTML = `<div class="empty-note">Could not load your reports: ${esc(e.message)}</div>`;
  }
}

function initPatient() {
  $("#eform").addEventListener("submit", submitReport);
  $("#clearReportBtn").addEventListener("click", clearReport);
}

/* ---------------- intake (coordinator) ---------------- */
function readFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("Could not read " + file.name));
    r.readAsText(file);
  });
}

async function handleNoteFile(file) {
  if (!file) return;
  state.intake.noteText = await readFile(file);
  state.intake.noteName = file.name;
  const d = $("#dropNote"); d.classList.add("loaded"); $("#nameNote").textContent = file.name;
  updateRunBtn();
}
async function handleLabsFile(file) {
  if (!file) return;
  const text = await readFile(file);
  try { state.intake.labsJson = JSON.parse(text); }
  catch { toast("Lab file is not valid JSON", true); return; }
  state.intake.labsName = file.name;
  const d = $("#dropLabs"); d.classList.add("loaded"); $("#nameLabs").textContent = file.name;
  updateRunBtn();
}
function updateRunBtn() {
  $("#runAgentsBtn").disabled = !(state.intake.noteText || state.intake.labsJson);
}
function clearIntake() {
  state.intake = { noteName: null, noteText: null, labsName: null, labsJson: null };
  $("#fileNote").value = ""; $("#fileLabs").value = "";
  $("#dropNote").classList.remove("loaded"); $("#dropLabs").classList.remove("loaded");
  $("#nameNote").textContent = ""; $("#nameLabs").textContent = "";
  $("#activityFeed").innerHTML = `<div class="activity-idle">Submit a record to watch ProtocolClaw and SafetyClaw run.</div>`;
  $("#intakeDone").hidden = true; $("#intakeDone").innerHTML = "";
  updateRunBtn();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function playActivity(activity, caseObj) {
  const feed = $("#activityFeed");
  feed.innerHTML = "";
  for (let i = 0; i < activity.length; i++) {
    const a = activity[i];
    const step = document.createElement("div");
    step.className = "act-step running";
    step.innerHTML = `<div class="act-dot"><span class="spinner"></span></div>
      <div class="act-body">
        <div class="act-agent">${esc(a.agent)} <span class="act-role">${esc(a.role)}</span></div>
        <div class="act-text">${esc(a.text)}</div>
        <div class="act-detail">${esc(a.detail || "")}</div>
      </div><span class="act-check">✓</span>`;
    feed.appendChild(step);
    await sleep(650);
    step.classList.remove("running"); step.classList.add("done");
    const dot = step.querySelector(".act-dot");
    dot.innerHTML = ["📡", "🚨", "📋", "📥"][i] || "✓";
    await sleep(200);
  }
  // success + handoff
  const done = $("#intakeDone");
  done.hidden = false;
  const devs = (caseObj.deviations || []).length;
  const severe = (caseObj.lab_findings || []).filter((l) => l.is_severe).length;
  done.innerHTML = `<div class="intake-success">
    <div class="is-h">✓ Case queued for review</div>
    <div class="is-sub"><b>${esc((caseObj.patient_meta || {}).patient_id || "Case")}</b> · ${devs} deviation(s) · ${severe} severe lab(s) · status <b>NEEDS_PI_REVIEW</b></div>
    <div class="is-sub">Sent to the <b>Principal Investigator</b>'s review inbox for adjudication.</div>
  </div>`;
  await loadQueue(true); // refresh counts/list in background
}

async function runIntake(sample) {
  const runBtn = $("#runAgentsBtn"), sampleBtn = $("#sampleBtn");
  runBtn.disabled = true; sampleBtn.disabled = true;
  try {
    let data;
    if (sample) {
      data = await api("/api/intake/sample", { method: "POST" });
    } else {
      data = await api("/api/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          note_name: state.intake.noteName, note_text: state.intake.noteText,
          labs_name: state.intake.labsName, labs_json: state.intake.labsJson,
        }),
      });
    }
    await playActivity(data.activity || [], data.case || {});
    toast("Agents finished · case queued ✓");
  } catch (e) {
    toast(e.message, true);
  } finally {
    sampleBtn.disabled = false;
    updateRunBtn();
  }
}

function initIntake() {
  const bind = (dropId, inputId, handler) => {
    const drop = $(dropId), input = $(inputId);
    drop.addEventListener("click", () => input.click());
    input.addEventListener("change", (e) => handler(e.target.files[0]));
    ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("dragover"); }));
    drop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) handler(e.dataTransfer.files[0]); });
  };
  bind("#dropNote", "#fileNote", handleNoteFile);
  bind("#dropLabs", "#fileLabs", handleLabsFile);
  $("#runAgentsBtn").addEventListener("click", () => runIntake(false));
  $("#sampleBtn").addEventListener("click", () => runIntake(true));
  $("#clearIntakeBtn").addEventListener("click", clearIntake);
}

/* ---------------- assistant workspace (3500A drafting) ---------------- */
const ws = { caseId: null, draft: "", messages: [], lastReply: null, docs: [], busy: false };

async function checkAssistant() {
  const dot = $("#chatDot"), label = $("#chatModel");
  try {
    const s = await api("/api/assistant/status");
    if (s.available) { dot.className = "chat-dot on"; label.textContent = `${s.model} · local vLLM`; }
    else { dot.className = "chat-dot off"; label.textContent = "model offline — will connect when up"; }
  } catch { dot.className = "chat-dot off"; label.textContent = "assistant unavailable"; }
}

function docPill(status) {
  if (status === "SIGNED") return `<span class="doc-pill signed">🔒 Signed</span>`;
  if (status === "DISMISSED") return `<span class="doc-pill dismissed">Dismissed</span>`;
  return `<span class="doc-pill pending">● In review</span>`;
}

async function loadDocs() {
  const { cases } = await api("/api/cases");
  ws.docs = cases || [];
  const list = $("#wsDocList");
  if (!ws.docs.length) { list.innerHTML = `<div class="ws-empty">No documents yet.</div>`; return; }
  list.innerHTML = ws.docs.map((d) => {
    const meta = d.patient_meta || {};
    return `<button class="ws-doc ${d.case_id === ws.caseId ? "active" : ""}" data-id="${esc(d.case_id)}" type="button">
      <div class="wd-pid">${esc(meta.patient_id || "?")} ${docPill(d.status)}</div>
      <div class="wd-id">${esc(d.case_id)}</div>
    </button>`;
  }).join("");
  list.querySelectorAll(".ws-doc").forEach((b) => b.addEventListener("click", () => selectDoc(b.dataset.id)));
}

function currentDoc() { return ws.docs.find((d) => d.case_id === ws.caseId); }

function renderWsMsgs() {
  const el = $("#wsMsgs");
  if (!ws.messages.length) {
    el.innerHTML = `<div class="ws-empty">Ask for a revision (“shorten Section B”, “add the dose-hold rationale”) or a question about this 3500A draft.</div>`;
    return;
  }
  el.innerHTML = ws.messages.map((m) => {
    const cls = m.role === "user" ? "user" : (m.offline ? "bot offline" : "bot");
    return `<div class="ws-msg ${cls}">${esc(m.content)}</div>`;
  }).join("");
  if (ws.busy) el.innerHTML += `<div class="ws-msg thinking">Assistant is drafting…</div>`;
  el.scrollTop = el.scrollHeight;
}

function selectDoc(caseId) {
  const doc = ws.docs.find((d) => d.case_id === caseId);
  if (!doc) return;
  ws.caseId = caseId;
  ws.draft = doc.draft_narrative || "";
  ws.messages = [];
  ws.lastReply = null;
  $("#wsDraft").value = ws.draft;
  const signed = doc.status === "SIGNED" || doc.status === "DISMISSED";
  $("#wsDocStatus").outerHTML = `<span id="wsDocStatus" class="doc-pill ${signed ? (doc.status === "SIGNED" ? "signed" : "dismissed") : "pending"}">${doc.status === "SIGNED" ? "🔒 Signed" : doc.status === "DISMISSED" ? "Dismissed" : "● In review"}</span>`;
  // Editing/iterating/signing the 3500A is a PRINCIPAL INVESTIGATOR action only.
  // Coordinator and Clinical Monitor open the workspace strictly read-only.
  const canEdit = !signed && ROLES[state.role].canSign;
  $("#wsDraft").readOnly = !canEdit;
  $("#wsSaveDraft").hidden = !canEdit;
  $("#wsSaveSign").hidden = !canEdit;
  $("#wsSend").disabled = !canEdit;
  $("#wsText").disabled = !canEdit;
  $("#wsText").placeholder = canEdit
    ? "e.g. Tighten Section B; add the dose-hold rationale…"
    : `Read-only — iterating the 3500A requires the Principal Investigator role.`;
  $("#wsApply").hidden = true;
  $("#wsReadonlyNote").hidden = canEdit;
  renderWsMsgs();
  loadDocs(); // refresh active highlight
}

async function openWorkspace(caseId) {
  $("#wsOverlay").hidden = false;
  document.body.style.overflow = "hidden";
  checkAssistant();
  await loadDocs();
  const target = caseId || (ws.docs[0] && ws.docs[0].case_id);
  if (target) selectDoc(target);
}

function closeWorkspace() {
  $("#wsOverlay").hidden = true;
  document.body.style.overflow = "";
}

async function wsSend() {
  const text = $("#wsText").value.trim();
  if (!text || ws.busy || !ws.caseId) return;
  ws.draft = $("#wsDraft").value; // capture any manual edits as context
  ws.messages.push({ role: "user", content: text });
  $("#wsText").value = "";
  ws.busy = true; renderWsMsgs();
  try {
    const res = await api("/api/narrative/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: ws.caseId, draft: ws.draft, messages: ws.messages }),
    });
    ws.messages.push({ role: "assistant", content: res.reply, offline: !res.available });
    ws.lastReply = res.available ? res.reply : null;
    $("#wsApply").hidden = !ws.lastReply;
    if (!res.available) checkAssistant();
  } catch (e) {
    ws.messages.push({ role: "assistant", content: "Error: " + e.message, offline: true });
  } finally {
    ws.busy = false; renderWsMsgs();
  }
}

function applyReply() {
  if (!ws.lastReply) return;
  $("#wsDraft").value = ws.lastReply;
  ws.draft = ws.lastReply;
  toast("Reply applied to draft — remember to Save");
}

async function saveDraft(silent) {
  if (!ws.caseId) return false;
  ws.draft = $("#wsDraft").value;
  try {
    await api(`/api/narrative/${encodeURIComponent(ws.caseId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft: ws.draft }),
    });
    // reflect in local state + the review inbox
    const doc = currentDoc(); if (doc) doc.draft_narrative = ws.draft;
    const pc = state.pending.find((c) => c.case_id === ws.caseId); if (pc) pc.draft_narrative = ws.draft;
    if (!silent) toast("Draft saved to MongoDB ✓");
    return true;
  } catch (e) { toast(e.message, true); return false; }
}

async function saveAndSign() {
  if (!ws.caseId) return;
  const btn = $("#wsSaveSign"); btn.disabled = true; btn.textContent = "Signing…";
  const ok = await saveDraft(true);
  if (!ok) { btn.disabled = false; btn.textContent = "Save & Submit (Sign)"; return; }
  try {
    const { audit } = await api(`/api/sign/${encodeURIComponent(ws.caseId)}`, { method: "POST" });
    toast(`Signed & locked · ${audit.audit_id} ✓`);
    await loadDocs();
    selectDoc(ws.caseId); // now shows Signed, read-only
    await loadQueue(true); // refresh inbox/KPIs behind the overlay
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Save & Submit (Sign)";
  }
}

function initWorkspace() {
  $("#wsClose").addEventListener("click", closeWorkspace);
  $("#wsOverlay").addEventListener("click", (e) => { if (e.target.id === "wsOverlay") closeWorkspace(); });
  $("#wsSend").addEventListener("click", wsSend);
  $("#wsText").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) wsSend(); });
  $("#wsApply").addEventListener("click", applyReply);
  $("#wsSaveDraft").addEventListener("click", () => saveDraft(false));
  $("#wsSaveSign").addEventListener("click", saveAndSign);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#wsOverlay").hidden) closeWorkspace(); });
}

/* ---------------- patient registry ---------------- */
const PHASE_OPTIONS = ["Phase 1", "Phase 2", "Phase 3"];

function statusChip(caseStatus) {
  const s = String(caseStatus || "").toUpperCase();
  if (s === "SIGNED") return `<span class="chip ok">🔒 Signed</span>`;
  if (s === "NEEDS_PI_REVIEW") return `<span class="chip major">● In review</span>`;
  if (s === "DISMISSED") return `<span class="chip mut">Dismissed</span>`;
  return `<span class="chip mut">No case</span>`;
}

function renderRegistryForm() {
  const wrap = $("#registryForm");
  if (!wrap) return;
  const canManage = !!ROLES[state.role].canManagePatients;
  if (!canManage) { wrap.hidden = true; wrap.innerHTML = ""; return; }
  wrap.hidden = false;
  const phaseOpts = PHASE_OPTIONS.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
  wrap.innerHTML = `
    <div class="card-h"><span class="ch-badge safety">➕</span>
      <div><h2>Add patient</h2><div class="ch-sub">Enroll a study subject into the registry.</div></div>
    </div>
    <div class="card-body">
      <div class="reg-form-grid">
        <label class="eform-field"><span class="ef-label">Subject ID</span>
          <input class="ef-input" id="regId" placeholder="PT-012"></label>
        <label class="eform-field"><span class="ef-label">Phase</span>
          <select class="ef-input" id="regPhase">${phaseOpts}</select></label>
        <label class="eform-field"><span class="ef-label">Site</span>
          <input class="ef-input" id="regSite" placeholder="Site 07 — Dell Medical Oncology"></label>
        <label class="eform-field"><span class="ef-label">Enrollment status</span>
          <input class="ef-input" id="regEnroll" placeholder="Screening"></label>
        <label class="eform-field"><span class="ef-label">Age</span>
          <input class="ef-input" id="regAge" type="number" min="0" placeholder="62"></label>
        <label class="eform-field"><span class="ef-label">Sex</span>
          <select class="ef-input" id="regSex"><option value="">—</option><option>Male</option><option>Female</option><option>Other</option></select></label>
        <label class="eform-field reg-form-wide"><span class="ef-label">Diagnosis</span>
          <input class="ef-input" id="regDx" placeholder="Refractory metastatic colorectal adenocarcinoma"></label>
      </div>
      <div class="intake-actions">
        <button class="btn primary" id="regAddBtn" type="button">➕ Add patient</button>
      </div>
    </div>`;
  $("#regAddBtn").addEventListener("click", addPatient);
}

async function addPatient() {
  const id = $("#regId").value.trim();
  if (!id) { toast("Subject ID is required", true); return; }
  const ageVal = $("#regAge").value.trim();
  const payload = {
    patient_id: id,
    phase: $("#regPhase").value,
    site: $("#regSite").value.trim() || null,
    enrollment_status: $("#regEnroll").value.trim() || null,
    age: ageVal ? Number(ageVal) : null,
    sex: $("#regSex").value || null,
    diagnosis: $("#regDx").value.trim() || null,
  };
  const btn = $("#regAddBtn"); btn.disabled = true; btn.textContent = "Adding…";
  try {
    await api("/api/patients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    toast(`Patient ${id} added ✓`);
    await loadRegistry();
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false; btn.textContent = "➕ Add patient";
  }
}

async function removePatient(patientId) {
  if (!confirm(`Remove ${patientId} from the registry? This cannot be undone.`)) return;
  try {
    await api(`/api/patients/${encodeURIComponent(patientId)}`, { method: "DELETE" });
    toast(`Patient ${patientId} removed`);
    await loadRegistry();
  } catch (e) {
    toast(e.message, true);
  }
}

async function loadRegistry() {
  renderRegistryForm();
  const el = $("#registryTable");
  const canManage = !!ROLES[state.role].canManagePatients;
  el.innerHTML = `<div class="empty-note">Loading…</div>`;
  try {
    const { patients } = await api("/api/patients");
    if (!patients.length) {
      el.innerHTML = `<div class="empty-note">No patients enrolled yet.${canManage ? "<br>Use the form above to add a subject." : ""}</div>`;
      return;
    }
    const rows = patients
      .map((p) => {
        const demo = [p.age != null ? `${esc(p.age)}` : "?", (p.sex || "")[0] ? esc((p.sex || "")[0]) : ""].join("");
        return `<tr>
          <td class="an">${esc(p.patient_id)}</td>
          <td><span class="phase-chip">${esc(p.phase || "Phase 1")}</span></td>
          <td>${statusChip(p.case_status)}</td>
          <td>${esc(p.site || "—")}</td>
          <td>${esc(p.enrollment_status || "—")}</td>
          <td class="num">${demo || "—"}</td>
          <td>${esc(p.diagnosis || "—")}</td>
          ${canManage ? `<td class="reg-actions"><button class="btn danger reg-remove" data-id="${esc(p.patient_id)}" type="button">Remove</button></td>` : ""}
        </tr>`;
      })
      .join("");
    el.innerHTML = `<table class="registry-table">
      <thead><tr>
        <th>Subject ID</th><th>Phase</th><th>Case status</th><th>Site</th>
        <th>Enrollment</th><th>Age/Sex</th><th>Diagnosis</th>${canManage ? "<th></th>" : ""}
      </tr></thead>
      <tbody>${rows}</tbody></table>`;
    if (canManage) {
      el.querySelectorAll(".reg-remove").forEach((b) =>
        b.addEventListener("click", () => removePatient(b.dataset.id))
      );
    }
  } catch (e) {
    el.innerHTML = `<div class="empty-note">Could not load the registry: ${esc(e.message)}</div>`;
  }
}

/* ---------------- roles (loaded from MongoDB care_team) ---------------- */
async function loadUsers() {
  try {
    const { users } = await api("/api/users");
    (users || []).forEach((u) => {
      if (!u.user_id) return;
      const prev = ROLES[u.user_id] || {};
      ROLES[u.user_id] = {
        name: u.name, title: u.title, initials: u.initials,
        nav: u.nav || prev.nav || ["inbox", "signed"],
        defaultView: u.default_view || prev.defaultView || "inbox",
        canSign: !!u.can_sign,
        // Patient-management capability: coordinator only. Prefer an explicit
        // Mongo flag; fall back to the hardcoded default so gating survives even
        // if the care_team doc predates this field.
        canManagePatients: u.can_manage_patients != null ? !!u.can_manage_patients : !!prev.canManagePatients,
      };
    });
  } catch { /* keep the hardcoded fallback ROLES */ }
}

function applyRole(role, forceDefault) {
  state.role = role;
  localStorage.setItem("careclaw_role", role);
  const r = ROLES[role];
  $("#roleSelect").value = role;
  $("#roleAvatar").textContent = r.initials;
  $("#roleName").textContent = r.name;
  $("#roleTitle").textContent = r.title;
  // gate nav
  document.querySelectorAll(".nav-item").forEach((n) => { n.hidden = !r.nav.includes(n.dataset.view); });
  // pick a view: forced default (first load), else keep current if still allowed
  const current = document.querySelector(".nav-item.active");
  const currentView = current ? current.dataset.view : null;
  if (forceDefault || !currentView || !r.nav.includes(currentView)) setView(r.defaultView);
  // ALWAYS re-render the case detail so the sign/chat/read-only gating matches the
  // new role — setView() alone leaves a stale actionbar from the previous role.
  renderDetail();
}

/* ---------------- view switching ---------------- */
const VIEW_COPY = {
  intake: ["New Record Intake", "Submit a clinical note and labs — CareClaw agents run and queue a case for the PI."],
  inbox: ["Review Inbox", "Cases processed by CareClaw agents, awaiting adjudication."],
  registry: ["Patient Registry", "Enrolled study subjects, trial phase, and current case status."],
  signed: ["Signed & Locked Records", "21 CFR Part 11 electronic records with cryptographic SHA-256 signatures."],
  submit: ["Submit Your Study eDiary", "Report today's vitals and how you're feeling — your study care team reviews every entry."],
  myreports: ["My Reports", "Your submitted eDiary entries and their status."],
};
function setView(view) {
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === view));
  $("#intakeView").hidden = view !== "intake";
  $("#inboxView").hidden = view !== "inbox";
  $("#registryView").hidden = view !== "registry";
  $("#signedView").hidden = view !== "signed";
  $("#submitView").hidden = view !== "submit";
  $("#myReportsView").hidden = view !== "myreports";
  // Hide the KPI row on non-PI-workflow views (intake + registry + patient views).
  $("#kpis").hidden = view === "intake" || view === "registry" || view === "submit" || view === "myreports";
  const [t, s] = VIEW_COPY[view] || VIEW_COPY.inbox;
  $("#pageTitle").textContent = t;
  $("#pageSub").textContent = s;
  if (view === "signed") loadSigned();
  if (view === "registry") loadRegistry();
  if (view === "submit") loadPatientForm();
  if (view === "myreports") loadMyReports();
}

/* ---------------- init ---------------- */
document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", () => { if (!n.hidden) setView(n.dataset.view); }));
$("#roleSelect").addEventListener("change", (e) => applyRole(e.target.value));
$("#refreshBtn").addEventListener("click", async () => {
  const b = $("#refreshBtn"); b.disabled = true; b.textContent = "↻ Refreshing…";
  await loadQueue(true);
  b.disabled = false; b.textContent = "↻ Refresh queue";
  toast("Queue refreshed");
});

initIntake();
initWorkspace();
initPatient();
(async () => {
  await loadUsers();               // hydrate ROLES from MongoDB care_team
  applyRole(state.role, true);
  await loadQueue(false).catch((e) => toast("Could not load queue: " + e.message, true));
})();
// gentle auto-poll so new cases appear across actors; only re-renders on change
setInterval(() => { if (!$("#inboxView").hidden) loadQueue(true, state.showingLock, true).catch(() => {}); }, 4000);
