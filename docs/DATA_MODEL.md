# CareClaw — MongoDB Data Model

MongoDB (`localhost:27017`) is the **single source of truth**. Access goes through
`store/careclaw_store.py` (`CareClawStore`, pymongo). Two databases on one instance:

- **`careclaw`** — operational data (this doc).
- **`nemoclaw_rag`** — the RAG corpus: collection `chunks` (protocol docs, `$text` index).
  Populated by `make ingest`, queried by `make query`. Retrieval-only; **not on the live path.**

DB name is overridable via `CARECLAW_DB` (tests use a throwaway db and drop it).

---

## Collections (`careclaw` db)

### `patients` — trial roster (one doc per subject)
| field | example | notes |
| --- | --- | --- |
| `patient_id` *(unique)* | `PT-004` | |
| `phase` | `Phase 1` | per-subject; shown as a chip across views |
| `age`, `sex`, `diagnosis` | `62`, `Male`, `mCRC` | demographics |
| `protocol_id`, `study_drug`, `study_arm` | `ONCO-2026-X88` | enrollment |
| `site`, `enrollment_status`, `c1d1_date` | `Site 07`, `Active` | |
| `baseline_labs` | `{ALT:28,...}` | for trend deltas |

### `cases` — intake documents / review queue (one doc per case)
| field | notes |
| --- | --- |
| `case_id` *(unique)* | dedup-suffixed (`-2`,`-3`) on collision |
| `status` | `NEEDS_PI_REVIEW` \| `SIGNED` \| `DISMISSED` |
| `patient_meta` | `{patient_id, phase, age, sex, study_day, protocol_id, ...}` |
| `deviations[]` | ProtocolClaw findings (category, severity, protocol_section, details) |
| `lab_findings[]` | SafetyClaw CTCAE grades (analyte, value, uln_multiple, ctcae_grade, is_severe) |
| `symptoms_mapped[]` | MedDRA PT + code |
| `draft_narrative` | the FDA 3500A text (deterministic, then LLM-upgraded) |
| `narrative_source` / `narrative_model` | `deterministic` \| `llm` / `qwen3.8-27b` |
| `note_text`, `lab_data` | the stored uploaded content |
| `source_files[]`, `trigger`, `report_id`, `created_at` | provenance (`trigger` set for ePRO-originated cases) |

The **PI review queue** = `cases` where `status = NEEDS_PI_REVIEW` (newest first).

### `events` — append-only audit log (the Part 11 spine)
`{ event, ts, case_id?/patient_id?/report_id?, ...payload }`

| `event` | written by | payload highlights |
| --- | --- | --- |
| `CASE_ENQUEUED` | OpenClaw intake | deviation/severe-lab counts |
| `NARRATIVE_UPGRADED` | intake bg upgrade | `narrative_source=llm`, model |
| `PATIENT_VITAL_ALERT` | VitalCheckClaw | severity, flags, summary |
| `REPORT_GENERATED` | ReportClaw | narrative_source, severity |
| `CASE_SIGNED` | PI sign | full `audit_record` (SHA-256, signer, ts, `APPROVED_AND_LOCKED`) |
| `CASE_DISMISSED` | PI dismiss | case_id |

### `care_team` — the demo actors / RBAC (one doc per role)
`{ user_id, name, title, initials, nav[], default_view, can_sign, can_manage_patients, order }`
The frontend hydrates its role config from here (`/api/users`). Gating is frontend-side
(no server auth — consistent with a single-site demo).

| role | nav | can_sign | can_manage_patients |
| --- | --- | --- | --- |
| `coordinator` | intake, inbox, registry, signed | ❌ | ✅ |
| `pi` | inbox, registry, signed | ✅ | ❌ |
| `monitor` (CRA) | inbox, registry, signed | ❌ | ❌ |
| `patient` *(frontend-only)* | submit, myreports | ❌ | ❌ |

### `patient_reports` — ePRO / eDiary submissions (one doc per submission)
`{ report_id (unique), patient_id, submitted_at, vitals{}, symptoms[], meds, observations, triage{}, concern_summary }`
Indexed by `(patient_id, submitted_at desc)`. Concerning submissions trigger the
`PATIENT_VITAL_ALERT` → ReportClaw chain.

---

## Read / write matrix

| Component | patients | cases | events | care_team | patient_reports |
| --- | --- | --- | --- | --- | --- |
| OpenClaw intake (`watcher.py`) | R (phase) · W (upsert) | **W** | W `CASE_ENQUEUED` | R | — |
| Intake bg upgrade (`server.py`) | — | **W** (narrative) | W `NARRATIVE_UPGRADED` | — | — |
| VitalCheckClaw (`patient_triage`) | — | — | W `PATIENT_VITAL_ALERT` | — | R/W |
| ReportClaw (`report_claw.py`) | R | **W** (enqueue) | W `REPORT_GENERATED` | — | R |
| PI sign / dismiss (`server.py`) | — | W (status) | W `CASE_SIGNED`/`_DISMISSED` | — | — |
| Registry (`/api/patients`) | **R/W** (add/remove) | R (status join) | — | — | — |
| Web reads (`/api/queue`,`/signed`,`/users`,`/cases`) | R | R | R | R | R |

---

## API ↔ collection quick map
`/api/queue` `/api/cases` → `cases` · `/api/signed` → `events(CASE_SIGNED)` ·
`/api/sign` `/api/dismiss` `/api/narrative/*` → `cases`+`events` ·
`/api/intake[/sample]` → `cases`+`events`(+bg) · `/api/patients` → `patients` ·
`/api/users` → `care_team` · `/api/patient/report` `/api/patient/reports` → `patient_reports`(+`events`,+bg).

Seed everything: `make seed` (`scripts/seed_demo.py`) — **resets** the `careclaw` db to
1 PT-004 case, the care team, a 7-subject phased roster, and 2 ePRO reports.
