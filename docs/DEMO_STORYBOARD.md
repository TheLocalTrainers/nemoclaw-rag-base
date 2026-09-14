# CareClaw Hackathon Demo Storyboard
## Dell × NVIDIA AI Hackathon — 5 minutes (3 min live demo + 2 min Q&A)

Grounded in [`PITCH_DECK.md`](PITCH_DECK.md) and executable against the **current**
repo scaffold on `feat/careclaw-agent-pipeline`.

---

## 0. The story in one sentence

> A messy EHR note and STAT labs drop into an on-prem folder → an always-on
> OpenClaw daemon flags protocol anomalies (ProtocolClaw) and drafts a safety
> record (SafetyClaw) → a clinician reviews and 1-click signs → a SHA-256
> 21 CFR Part 11 audit lock is written locally. No cloud egress.

---

## 1. Pitch slides → what you show

| Pitch beat | Slide | Live artifact in this repo |
| --- | --- | --- |
| Thesis / pain | 1–2 | Speak only (cards on slides) |
| Architecture | 3 | Point at Dell box + this diagram; optionally flash `configs/openshell/careclaw_policy.yaml` |
| **LIVE DEMO** | **4** | Terminal daemon + Streamlit Review Queue (this storyboard) |
| Lifecycle / ROI | 5–6 | Speak only |
| Regulatory defense | 7 | Show Part 11 hash after sign-off |
| Ask | 8 | Close |

---

## 2. Connected architecture (what the demo actually runs)

```text
corpus/fixtures/patient_004_*.{txt,json}
        │  ./scripts/hackathon_demo_drop.sh
        ▼
incoming_records/                    ← EHR drop folder
        │
        ▼
python -m daemon.watcher             ← OpenClaw always-on sentinel
        │  ProtocolClaw  → deviations (window + ketoconazole)
        │  SafetyClaw    → CTCAE grade + MedDRA + FDA 3500A draft
        ▼
audit_logs/pending_reviews.jsonl     ← status: NEEDS_PI_REVIEW
        │
        ▼
streamlit run app.py                 ← PI Review Queue (HITL)
        │  Approve & Sign
        ▼
audit_logs/careclaw_events.jsonl     ← CASE_SIGNED + SHA-256 lock
```

Supporting (not required for the 3-minute path, but available if judges ask):

| Scaffold piece | Demo use |
| --- | --- |
| `corpus/protocol/onco_2026_x88.md` | “100-page protocol” narrative; RAG indexable via `make ingest` |
| `configs/clinical/protocol_rules.yaml` | Deterministic visit windows / con-med lists |
| `configs/clinical/meddra_mini.json` | Constrained MedDRA codes |
| `configs/openshell/careclaw_policy.yaml` | Show zero-egress policy intent |
| `rag/` + MongoDB | Optional: `make query Q="prohibited CYP3A4"` after ingest |
| NemoClaw / live OpenShell / vLLM | **Not required** for this storyboard; claim as target runtime on GB10 |

---

## 3. Pre-flight (T−10 minutes)

Run once before judges arrive:

```bash
cd ~/nemoclaw-rag-base
source .venv/bin/activate          # or: make venv first
pip install -e . && pip install -r requirements.txt
python -m unittest tests/test_protocol_claw.py tests/test_safety_claw.py -v
# Expect: 8 tests OK

# Clean slate for a crisp demo
mkdir -p incoming_records processed_records audit_logs
rm -f incoming_records/* processed_records/* \
      audit_logs/pending_reviews.jsonl
# Keep historical careclaw_events.jsonl or truncate if you want a clean tail:
: > audit_logs/careclaw_events.jsonl

chmod +x scripts/hackathon_demo_drop.sh
```

Open **three panes** on the Dell display:

| Pane | Command | Role |
| --- | --- | --- |
| **A — Daemon** | `python -m daemon.watcher` | Always-on intake |
| **B — Clinician UI** | `streamlit run app.py` | PI review gateway |
| **C — Drop** | idle until Beat 3 | Fixture drop |

In Streamlit sidebar: select **Review Queue (daemon)**.

---

## 4. Three-minute live run-of-show (Slide 4)

### Beat 0 — Set the scene (0:00–0:20) · speak over architecture slide

> “CareClaw sits at the site, air-gapped. Notes and labs land in a drop folder.
> Two agents act: ProtocolClaw flags deviations; SafetyClaw drafts the FDA filing.
> A physician still owns the signature.”

Point at Pane A (daemon watching) and Pane B (empty Review Queue).

### Beat 1 — The messy reality (0:20–0:40)

On slides or briefly open the fixture in an editor:

- `patient_004_visit_note.txt` — delayed **C1D14 on Study Day 19**, **ketoconazole**, RUQ pain / fatigue / scleral icterus
- `patient_004_labs.json` — **ALT 265** (~5.9× ULN), AST 230, bili 2.4

Say: “This is what sits unnoticed in charts until centralized monitoring — weeks later.”

### Beat 2 — Drop → autonomous agents (0:40–1:20)

In Pane C:

```bash
./scripts/hackathon_demo_drop.sh
```

**Watch Pane A.** Expected log lines within ~2 seconds:

```text
[!] CareClaw Daemon: Pairing 'patient_004_visit_note.txt' + 'patient_004_labs.json'...
    [+] ProtocolClaw identified 2 protocol deviation(s).
    [+] SafetyClaw generated draft FDA Form 3500A narrative.
    [✓] Queued for PI review → pending_reviews.jsonl (CASE-PT-004-...)
```

One paired case should appear (note + labs together), not two separate cases.

Narrate:

> “No human clicked ‘run model.’ OpenClaw saw the drop, ProtocolClaw scored the
> visit window and prohibited drug, SafetyClaw graded CTCAE and drafted 3500A —
> all on-box.”

### Beat 3 — Clinician inbox (1:20–2:20)

In Pane B:

1. Click **Refresh queue**
2. Open the PT-004 case
3. Call out on screen (matches pitch Slide 4 alert cards):

| Card | What judges must see |
| --- | --- |
| Visit window | C1D14 on **Day 19** vs window **Days 12–16** (MAJOR) |
| Con-med | **Ketoconazole** / Section **5.2.1** (CRITICAL) |
| Labs | ALT **Grade 3** (>5× ULN), dose-hold language |
| MedDRA | e.g. Abdominal pain upper / Fatigue / Ocular icterus codes |
| Narrative | Expandable FDA 3500A with causality checkboxes still **blank** |

Emphasize Slide 7 line: *“We never decide causality — the PI does.”*

### Beat 4 — 1-click Part 11 lock (2:20–2:50)

Click **Approve Deviation & Sign 3500A**.

Show success: Audit ID + **64-char SHA-256** + signer `PI-DR-VANCE-MD`.

Optional proof in Pane C:

```bash
tail -n 1 audit_logs/careclaw_events.jsonl | python3 -m json.tool | head -40
```

> “Cryptographic lock, local enclave, inspection-ready.”

### Beat 5 — Hand back to slides (2:50–3:05)

> “That’s front-end reconciliation in seconds instead of weeks — then we scale
> the same pattern across Phase 1–3 economics.”

Continue Slides 5–8.

---

## 5. Speaker cheat sheet (expected findings)

For PT-004 defaults hardcoded in fixtures / agents:

| Agent | Finding | Severity |
| --- | --- | --- |
| ProtocolClaw | Visit Window Non-Compliance (Day 19 vs 12–16) | MAJOR |
| ProtocolClaw | Prohibited Concomitant Medication — Ketoconazole | CRITICAL |
| SafetyClaw | ALT ~5.9× ULN → Grade 3; mandatory dose hold | Severe |
| SafetyClaw | MedDRA PTs from note text + lab codes | Coded |
| SafetyClaw | FDA 3500A zero-draft | Pending PI |
| UI sign | `APPROVED_AND_LOCKED` + SHA-256 | Part 11 |

Verify offline anytime:

```bash
python -m unittest tests/test_protocol_claw.py tests/test_safety_claw.py -v
```

---

## 6. Honesty table (demo vs pitch language)

Use this so you don’t overclaim under Q&A.

| Pitch claim | Demo reality in this scaffold |
| --- | --- |
| Always-on OpenClaw watcher | ✅ `daemon/watcher.py` polling `incoming_records/` |
| ProtocolClaw / SafetyClaw | ✅ Deterministic Python agents + YAML/JSON rules |
| 1-click clinician sign-off | ✅ Streamlit Review Queue → SHA-256 audit |
| Zero cloud egress | ✅ No outbound calls in this path; policy file shows intent |
| Local vLLM / Hermes / Qwen | ⚠️ **Not invoked** in the demo path — narrative is templated/deterministic |
| NemoClaw onboarded sandbox | ⚠️ Scaffold + policy YAML; full OpenShell sandbox optional |
| Mongo Protocol RAG | ✅ Available via `make smoke` / `make query`; **not required** in the 3-min path |
| “Generated in 1.4s by vLLM” | ❌ Do **not** say this in Review Queue mode; say “zero-draft scribe” |

If a judge asks “where’s the LLM?”:  
> “The compliance rules are deterministic by design for GAMP 5. The GB10/vLLM
> slot is for narrative polish and protocol RAG Q&A; today’s demo proves the
> regulated HITL loop that must work even when generation is constrained.”

---

## 7. Contingency paths

| Failure | Recovery |
| --- | --- |
| Daemon not running | Start Pane A; re-run drop script |
| Queue empty after drop | Check `incoming_records/` empty & `processed_records/` has files; read `pending_reviews.jsonl` |
| Streamlit wrong mode | Sidebar → **Review Queue (daemon)** |
| Need demo without daemon | Sidebar → **Manual Simulate** → Process (same PT-004 story, weaker narrative) |
| Tests failing | Fix before stage; do not live-debug with judges waiting |

---

## 8. Optional “judge deep-dive” (if asked)

```bash
# Protocol grounding
make mongo-up && make ingest
make query Q="what are the prohibited CYP3A4 inhibitors?"

# Policy
sed -n '1,80p' configs/openshell/careclaw_policy.yaml

# Unit proof
python -m unittest tests/test_protocol_claw.py tests/test_safety_claw.py -v
```

---

## 9. Roles for a two-person pitch

| Person | Owns |
| --- | --- |
| **Narrator** | Slides 1–3, 5–8 + Q&A |
| **Driver** | Panes A/B/C, drop script, click Refresh / Sign, tail audit log |

Rehearse twice with a stopwatch. The live demo must fit **≤ 3:00**.
