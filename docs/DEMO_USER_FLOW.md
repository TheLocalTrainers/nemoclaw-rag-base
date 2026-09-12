# CareClaw Demo — User Flow Breakdown (Tunable)

> Companion to [`DEMO_STORYBOARD.md`](DEMO_STORYBOARD.md). The storyboard is the run-of-show;
> this doc is the **UX spine** — a rehearsal script you can edit before stage.
> It describes the **new web console** (`web/`), which replaces the old terminal
> daemon + Streamlit path. Everything is now UI-driven: no drop scripts during the demo.
>
> Storage-agnostic on purpose. We describe what the **user sees and does** and what
> **conceptually gets written** (a queued case, a signed Part 11 lock) — not the JSONL/DB
> internals, which can change without touching this flow.

---

## 1. One-paragraph summary

A study coordinator (Sarah Kim, RN) opens the CareClaw console and lands on **New Intake**.
She either uploads a real EHR note (`.txt`) + lab panel (`.json`) or clicks **Use PT-004 sample**,
then presses **Run CareClaw agents**. On submit, the autonomous pipeline runs in-process on the
GB10 box and streams an animated activity timeline: **OpenClaw** pairs the note + labs into one
case, **ProtocolClaw** flags **2 protocol deviations** (a MAJOR visit-window miss and a CRITICAL
prohibited con-med), and **SafetyClaw** grades **2 severe labs** (ALT/AST at Grade 3), maps
**3 MedDRA terms**, and drafts a zero-draft FDA 3500A — leaving causality **blank**. The case is
queued `NEEDS_PI_REVIEW`. A one-click **"Review as Principal Investigator →"** handoff switches
roles to **Dr. Vance, MD**, who opens the case in **Review Inbox**, reads the ProtocolClaw deviation
cards, the SafetyClaw CTCAE labs table, the MedDRA chips, and the collapsible 3500A narrative, then
clicks **Approve Deviation & Sign 3500A**. That writes a **21 CFR Part 11 SHA-256 electronic lock**
locally and clears the case; it appears in **Signed Records**. Optionally, the **Clinical Monitor
(CRA)** switches in for a read-only view proving segregation of duties — the same case, no sign button.
No file leaves the machine at any step.

---

## 2. Actors

| Actor | Human/Agent | What they do | UI role | Views they use | Can sign? |
| --- | --- | --- | --- | --- | --- |
| **Sarah Kim, RN** (Study Coordinator) | Human | Opens the console, submits the note + labs (upload or PT-004 sample), watches agents run, hands the case off to the PI | `coordinator` (avatar **SK**) | New Intake → (Review Inbox, Signed Records visible but read-only) | No |
| **OpenClaw** | Autonomous agent | Always-on sentinel; receives the dropped files and **pairs note + labs into one case** (not two) | — (runs in-process; shown as activity step 1 📡) | Appears in New Intake activity feed | n/a |
| **ProtocolClaw** | Autonomous agent | Deterministic deviation sentinel; audits visit window (§8.1) and prohibited con-meds (§5.2) against `protocol_rules.yaml` | — (activity step 2 🚨) | Rendered as deviation cards in Review Inbox detail | n/a |
| **SafetyClaw** | Autonomous agent | FDA 3500A scribe; CTCAE v5.0 lab grading, MedDRA v27.0 mapping, zero-draft 3500A/CIOMS narrative, and the Part 11 SHA-256 record at sign time | — (activity step 3 📋) | Rendered as labs table + MedDRA chips + narrative in Review Inbox | n/a |
| **Dr. Vance, MD** (Principal Investigator) | Human | Adjudicates the case, reviews all agent output, decides causality, clicks **Approve & Sign** (or Dismiss) | `pi` (avatar **DV**) | Review Inbox (default), Signed Records | **Yes** |
| **J. Alvarez** (Clinical Monitor / CRA) | Human | Read-only oversight; can open the same cases and signed records but **cannot sign** — proves segregation of duties | `monitor` (avatar **JA**) | Review Inbox, Signed Records (both read-only) | No |

Role definitions live in `web/static/app.js` (`ROLES`); the role switcher is the **"Signed in as"**
dropdown in the sidebar.

---

## 3. Step-by-step flow (rehearsal script)

Times are the **target cadence** for a ≤3-minute live run; tune per §4. "Data written" is described
in UX terms (a queued case / a signed lock), not storage internals.

| # | Actor | Trigger | Action (what they click/do) | System / agent response | UI screen or state | Data written | Storyboard beat | Approx. time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Coordinator (SK) | Console opened at demo start | Nothing yet — console loads | App loads as **Study Coordinator**, lands on **New Intake**; KPI row hidden on intake; sidebar shows protocol card ONCO-2026-X88, Nexavatinib 200mg, C1D14 · Days 12–16, prohibited CYP3A4 inhibitors | New Intake view, empty state: "Submit a record to watch ProtocolClaw and SafetyClaw run." | — | Beat 0 (set the scene) | 0:00–0:15 |
| 1 | Coordinator (SK) | Narrator finishes "notes and labs land at the site" | **Option A:** drag `patient_004_visit_note.txt` into the note drop-zone and `patient_004_labs.json` into the labs drop-zone. **Option B (recommended for stage):** click **Use PT-004 sample** | Drop-zones show file names and turn "loaded"; **Run CareClaw agents** enables (Option A). Option B skips straight to the run | New Intake, both drop-zones filled OR sample armed | — (files held client-side; nothing persisted yet) | Beat 1 (the messy reality) | 0:15–0:35 |
| 2 | Coordinator (SK) | Files staged / sample chosen | Click **▶ Run CareClaw agents** (or the sample button runs directly) | POST to intake endpoint; agents run in-process on GB10; response returns the case + a 4-step activity script | New Intake, activity feed begins animating | A case is created and **queued `NEEDS_PI_REVIEW`** | Beat 2 (drop → autonomous agents) | 0:35–0:40 |
| 3 | OpenClaw | Agents invoked | (auto) | Activity step 1 📡 **OpenClaw · Always-on sentinel**: "Received patient_004_visit_note.txt, patient_004_labs.json" — detail: "Paired note + labs into one case." | Activity feed, step 1 spinner → ✓ | (part of the single queued case) | Beat 2 | +~0.9s |
| 4 | ProtocolClaw | OpenClaw done | (auto) | Activity step 2 🚨 **ProtocolClaw · Deviation sentinel**: "Identified **2** protocol deviation(s)" — detail: "Visit Window Non-Compliance, Prohibited Concomitant Medication" | Activity feed, step 2 spinner → ✓ | Deviations attached to the case | Beat 2 | +~0.9s |
| 5 | SafetyClaw | ProtocolClaw done | (auto) | Activity step 3 📋 **SafetyClaw · FDA 3500A scribe**: "Graded **2** lab(s) · **2** severe · mapped **3** MedDRA term(s)" — detail: "Drafted FDA Form 3500A zero-draft (causality left blank)." | Activity feed, step 3 spinner → ✓ | CTCAE grades, MedDRA terms, draft narrative attached | Beat 2 | +~0.9s |
| 6 | Queue (handoff) | SafetyClaw done | (auto) | Activity step 4 📥 **Queue · Handoff**: "Queued for PI review · CASE-PT-004-2026-09-08-…" — detail: "Status NEEDS_PI_REVIEW — awaiting a physician signature." Then a green success card: "✓ Case queued for review · **PT-004** · 2 deviation(s) · 2 severe lab(s) · status NEEDS_PI_REVIEW" with a **Review as Principal Investigator →** button | Activity feed complete + success card; nav "Review Inbox" count ticks to 1 | Case fully queued; nav counters update | Beat 2 → 3 | +~0.9s (feed total ≈ 3.4s) |
| 7 | Coordinator → PI | Success card shown | Click **Review as Principal Investigator →** (this is the choreographed role handoff) | Role switches to **Dr. Vance, MD** (DV); view switches to **Review Inbox** with the PT-004 case pre-selected | Review Inbox; topbar now "Principal Investigator Review Inbox"; KPI row visible | — (role/session state only) | Beat 3 (clinician inbox) | 0:40–1:20 |
| 8 | PI (DV) | Inbox open | Read the KPI row and the case card | KPIs: **1** Cases awaiting review · **2** Protocol deviations flagged · **1** Critical severity alert · **0** Signed. Case card shows **PT-004 · Study Day 19 · ONCO-2026-X88 · 62M** with chips **● CRITICAL**, **2 deviations**, **Grade 3 lab** | Review Inbox, queue list + KPIs | — | Beat 3 | 1:20–1:30 |
| 9 | PI (DV) | Case selected | Read **ProtocolClaw — Deviation Sentinel** card | Card 1 🔴 **Visit Window Non-Compliance** [MAJOR] — §8.1: "Cycle 1 Day 14 safety visit performed on Study Day 19… window Days 12 to 16… 3 day(s) outside window." Card 2 🔴 **Prohibited Concomitant Medication: Ketoconazole** [CRITICAL] — §5.2.1: increases Nexavatinib exposure >3.5×, action = withhold study drug + PI notification | Review Inbox detail, ProtocolClaw section (2 findings) | — (reading) | Beat 3 | 1:30–1:50 |
| 10 | PI (DV) | Scrolls detail | Read **SafetyClaw — FDA 3500A Scribe** labs table + MedDRA chips | Labs table: **ALT 265 U/L · 5.9× ULN · Grade 3 (Severe)** (baseline 28 ▲); **AST 230 U/L · 5.8× ULN · Grade 3** (baseline 24 ▲); both rows severe-highlighted. MedDRA chips: **Abdominal pain upper**, **Fatigue**, **Ocular icterus** (+ ALT/AST increased codes) | Review Inbox detail, SafetyClaw section | — | Beat 3 | 1:50–2:05 |
| 11 | PI (DV) | Scrolls to narrative | Expand/read **Pre-drafted FDA 3500A / CIOMS I narrative** (collapsible) | Monospace 3500A zero-draft: demographics, AE narrative with lab lines, MedDRA section, "MANDATORY Nexavatinib DOSE HOLD… Section 6.2", and Section E with **causality checkboxes blank** + "[PENDING 1-CLICK AUTHENTICATED SIGN-OFF]". Footer reminder: "⚖️ Causality & action fields remain **blank** — CareClaw never decides causality. The PI does." | Review Inbox detail, narrative card (expanded) | — | Beat 3 (Slide 7 line) | 2:05–2:20 |
| 12 | PI (DV) | Review complete | Click **🔒 Approve Deviation & Sign 3500A** | Button → "Signing…"; SafetyClaw generates the Part 11 record; toast "Electronic record signed & locked ✓"; case removed from queue | Review Inbox → lock confirmation panel replaces detail | **Signed Part 11 record written locally** (status APPROVED_AND_LOCKED) | Beat 4 (1-click Part 11 lock) | 2:20–2:35 |
| 13 | PI (DV) | Sign succeeded | Read the lock panel | 🔒 **Electronic Record Signed & Locked**: Status **APPROVED_AND_LOCKED**, Audit ID `AUDIT-…`, Signer **PI-DR-VANCE-MD**, UTC timestamp, Standard **FDA 21 CFR Part 11**, and the full **64-char SHA-256** hash | Lock confirmation panel; KPI "Signed & Part 11 locked" ticks to 1, pending → 0 | (already written) | Beat 4 | 2:35–2:45 |
| 14 | PI (DV) | Wants durable proof | Click **Signed Records** in nav | Signed-record row: Audit ID, PT-004 · Study Day 19 · PI-DR-VANCE-MD · timestamp, **🔒 APPROVED_AND_LOCKED**, and the SHA-256 hash | Signed Records view | — (reads the locked record) | Beat 4 → 5 | 2:45–2:55 |
| 15 | *(optional)* Monitor (JA) | Judge asks "who else can see this?" | Switch **"Signed in as" → Clinical Monitor (CRA)**, open the case / signed records | Same case + signed records render, but the action bar shows **"👁 Review-only… Electronic sign-off requires the Principal Investigator role"** — no sign button | Review Inbox / Signed Records, read-only | — | Beat 5 (segregation of duties) | +0:10 |
| 16 | Narrator | Demo done | Hand back to slides | — | — | — | Beat 5 (hand back) | 2:55–3:05 |

**Fastest path (single click, ~2 min):** Coordinator clicks **Use PT-004 sample** (steps 1–2 collapse
into one), watches the feed (steps 3–6), clicks the handoff (step 7), skims (steps 8–11), signs (step 12).
Steps 14–15 are optional.

---

## 4. Tuning knobs (levers we can turn before stage)

- **Activity-step pacing.** Each of the 4 steps runs `~650ms spinner + ~200ms settle` (`playActivity`
  in `app.js`, `sleep(650)` / `sleep(200)`). Total feed ≈ **3.4s**. Slow it down for drama (narration
  room) or speed it up to keep under time. This is the single biggest "feel" lever.
- **Upload vs one-click sample.** For a live audience, **Use PT-004 sample** is the safe, deterministic
  path (no file-picker fumbling). Keep upload for the "it works on real messy files" beat, or if a judge
  hands you a file. Decide which to show — or show sample live and mention upload verbally.
- **Which findings to emphasize.** Four hero findings exist; pick 2–3 to narrate so you don't run long:
  (a) visit window Day 19 vs 12–16 MAJOR, (b) **ketoconazole CRITICAL §5.2.1** (the CYP3A4 story is the
  strongest), (c) ALT 5.9× ULN Grade 3 dose-hold, (d) causality-blank narrative. The ketoconazole +
  ALT pair tells the cleanest cause→effect story.
- **Role-handoff choreography.** The **Review as Principal Investigator →** button is the seam between
  the two actors. For a **two-person pitch**, the driver clicks intake, the second presenter "becomes"
  the PI. For a **one-person pitch**, the same person clicks the handoff and narrates the role change.
  Rehearse who clicks what.
- **Narration cue points.** Natural pauses: after step 6 (case queued) before the handoff; after step 11
  (narrative) before signing — this is where the "we never decide causality" line lands. Mark these in
  the script.
- **Empty-state → populated transition.** Start with a truly empty queue (0 KPIs, "Queue is empty")
  so the case *appearing* is visible. Pre-flight should clear pending cases so the count starts at 0.
- **KPIs to surface.** The KPI row shows Pending / Deviations / Critical / Signed. Decide whether to
  call them out (good for "at-a-glance monitoring") or let them speak for themselves.
- **Which role you open in.** Default is Coordinator on New Intake (best for the full narrative). To do a
  PI-only short version, you could open as PI — but you'd lose the intake/handoff beat. Recommend keeping
  Coordinator-first.
- **Monitor cameo on/off.** Step 15 is a strong "segregation of duties / 21 CFR" proof if a judge probes
  governance, but it's optional and adds ~10s. Keep it in your back pocket.
- **Auto-poll cadence.** The inbox background-refreshes every 4s (`setInterval` in `app.js`); relevant if
  you run intake and PI on two screens/tabs so the case appears without a manual refresh.
- **Signer identity.** Hard-coded `PI-DR-VANCE-MD`. Change if you want the on-screen signer to match your
  presenter's persona.

---

## 5. Mapping to storyboard beats (old terminal path → new UI path)

| Beat | Storyboard (old, terminal-driven) | New UI-driven flow | What changed |
| --- | --- | --- | --- |
| **0 — Set the scene** | Point at Pane A (daemon) + Pane B (empty Streamlit queue) | Console open as Coordinator on **New Intake**, empty activity feed; sidebar protocol card visible | No terminal panes. One browser window; the "always-on" story is told by the OpenClaw activity step, not a live daemon log |
| **1 — The messy reality** | Open `patient_004_*` fixtures in an editor / on slides | Coordinator stages the same note + labs in the intake drop-zones (or arms the PT-004 sample) | The messy note is now *in the product*, ready to submit — not a side artifact |
| **2 — Drop → autonomous agents** | Run `./scripts/hackathon_demo_drop.sh`; watch daemon log lines in Pane A | Click **Run CareClaw agents** / **Use PT-004 sample**; watch the in-UI 4-step activity timeline (OpenClaw → ProtocolClaw → SafetyClaw → Queue) | **No drop script.** The coordinator drives intake in the UI; agent progress is a designed animation, not scrollback |
| **3 — Clinician inbox** | Streamlit "Refresh queue" → open case → read alert cards | **Review as PI →** handoff → Review Inbox detail: deviation cards, CTCAE labs table, MedDRA chips, collapsible 3500A | Role handoff is explicit and one-click; same findings, richer layout. Refresh is automatic (4s poll) but a manual **↻ Refresh queue** button exists |
| **4 — 1-click Part 11 lock** | Streamlit **Approve & Sign** → success with SHA-256; optional `tail` of JSONL | **Approve Deviation & Sign 3500A** → in-app lock panel (Audit ID, signer, 64-char SHA-256) → **Signed Records** view | Same cryptographic lock; proof is now a first-class **Signed Records** screen, no terminal `tail` needed |
| **5 — Hand back / governance** | Hand back to slides | Hand back to slides; **optional** Clinical Monitor read-only cameo to prove segregation of duties | New optional monitor role adds a governance beat the terminal demo didn't have |

Honesty note carries over unchanged: the narrative is **deterministic/templated**, not live-LLM. Don't say
"generated in 1.4s by vLLM" — say "zero-draft scribe." The GB10/vLLM slot remains the target runtime claim.

---

## 6. Open questions / risks to tune before stage

- **Backend must be running.** The console needs the FastAPI server up (`uvicorn web.server:app --port 8000`).
  Unlike the old two-pane setup, there's no separate daemon to babysit — but if the server is down, intake
  and signing fail. Add "server up + page loads" to pre-flight.
- **Storage/persistence dependency.** Signing and queueing read/write the on-disk audit artifacts (and Mongo
  if wired for RAG side-quests). Confirm whatever store the deployed build uses is running and **writable**;
  a read-only or missing audit dir makes **Approve & Sign** fail silently to the user (toast error only).
- **Clean starting state.** Clear any leftover pending cases so the queue starts at **0** and the case
  visibly appears. A stale queue (multiple PT-004 cases) muddies the "one paired case" story.
- **Duplicate-case risk.** Re-running the sample enqueues **another** PT-004 case each time (case_id includes
  the file stems, so repeated sample runs collide/stack). Between rehearsals, clear the queue.
- **Role-switch choreography.** For a two-person pitch, decide who holds the mouse across the Coordinator→PI
  seam. For one person, practice narrating "now I'm the PI." The handoff button makes this smooth but it's
  still a rehearsed moment.
- **One-screen vs two-screen.** If you demo intake on one screen and PI on another (two tabs), rely on the
  4s auto-poll — or click **↻ Refresh queue**. On a single screen, the handoff button is instant and safer.
- **"Where's the LLM?" question.** Same as storyboard: rules are deterministic by design for GAMP 5; the
  narrative is a zero-draft scribe. Have the honesty-table answer ready.
- **Time budget.** Full 16-step path with narration can drift past 3:00. If tight, use the fast path
  (§3 note) and drop the monitor cameo (step 15).
- **Browser/display.** Confirm fonts load (IBM Plex Mono / Plus Jakarta Sans are fetched from Google Fonts).
  If the venue is truly air-gapped, the fonts fall back to system stacks — verify the layout still looks clean
  offline, since "100% LOCAL / NETWORK ISOLATED" badges are on screen.
- **Causality-blank must be visible.** The strongest regulatory line ("we never decide causality") depends on
  the PI seeing the blank checkboxes. Make sure the narrative card is expanded (it defaults open) when you
  deliver that line.
```
