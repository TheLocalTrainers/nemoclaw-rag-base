# CareClaw / nemoclaw-rag-base

**Sovereign Clinical Trial Compliance & Safety Copilot** pairing a **MongoDB Protocol RAG scaffold** with **NemoClaw / OpenShell / OpenClaw / Hermes** agent wiring on the **Dell Pro Max with NVIDIA GB10**.

Eliminating the front-end data reconciliation lag in clinical trial operations — **100% locally with zero cloud egress**.

> 🎤 **Preparing for the 5-minute pitch? Read [`docs/PITCH_DECK.md`](docs/PITCH_DECK.md) for the complete 8-slide deck, speaker talk tracks, and judge Q&A defense.**

---

## What CareClaw Does

Clinical trial coordinators and centralized data managers spend hundreds of hours manually reconciling unstructured progress notes and lab reports against 100-page protocols. CareClaw runs as an air-gapped, always-on administrative sentinel:

1. **Protocol Deviation Sentinel (`ProtocolClaw`)**: Performs deterministic study day math to catch out-of-window lab visits (e.g. C1D14 allowable window: Days 12–16) and scans unstructured notes for prohibited concomitant medications (e.g. potent CYP3A4 inhibitors like ketoconazole) with exact protocol citations.
2. **Adverse Event Scribing (`SafetyClaw`)**: Evaluates laboratory transaminases against NCI CTCAE v5.0 thresholds (e.g. ALT $>5\times$ ULN = Grade 3), maps symptoms to official MedDRA v27.0 Preferred Terms, and pre-drafts standard **FDA MedWatch Form 3500A / CIOMS I** safety narratives.
3. **1-Click Clinician Review & Sign-Off**: Compliant with **FDA 21 CFR Part 11**, recording cryptographic SHA-256 hashes for all accepted deviations and signed safety filings.
4. **Zero Cloud Egress via NVIDIA OpenShell**: Isolated at the kernel level (`network.egress: blocked` except localhost vLLM and MongoDB), guaranteeing protected health information (PHI) never leaves on-premise hardware.

---

## Quickstart: CareClaw Live Demo

### 1. Prerequisites & Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements.txt
```

### 2. Run the Interactive Streamlit Demo UI

```bash
streamlit run app.py
```
* Simulates incoming EHR doctor notes and STAT CMP lab results.
* Displays real-time **Important Protocol Deviation** alerts.
* Displays pre-drafted **FDA Form 3500A** narratives.
* Provides 1-click Principal Investigator electronic sign-off with SHA-256 audit logging.

### 3. Run the Always-On Background Daemon

```bash
python3 -m daemon.watcher
```
Runs an autonomous file listener monitoring `incoming_records/`. When an EHR note (`.txt`) or lab result (`.json`) drops into the directory, it executes the pipeline within milliseconds and archives the event into `audit_logs/careclaw_events.jsonl`.

### 4. Run Unit Tests (Agent Suite)

```bash
python3 -m unittest tests/test_protocol_claw.py tests/test_safety_claw.py
```
Runs 8 deterministic unit tests verifying visit window calculations, drug ontology matching, CTCAE grading, MedDRA symptom extraction, and 21 CFR Part 11 cryptographic hashing.

---

## Core RAG & MongoDB Infrastructure

The repository also includes the foundational host RAG engine for indexing and querying clinical study protocols into MongoDB.

```bash
# Start MongoDB (Docker or local binary fallback)
make mongo-up

# Ingest clinical protocol & fixture corpus into MongoDB
make ingest

# Query the protocol RAG index directly
make query Q="what are the prohibited CYP3A4 inhibitors?"

# Run smoke test verifying MongoDB ingest and retrieval
make smoke
```

---

## Stack Architecture

```text
[Incoming EHR Notes & Lab Results]
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│             Dell Pro Max with NVIDIA GB10              │
│                                                        │
│  ┌────────────────────────┐    ┌────────────────────┐  │
│  │  OpenClaw Always-On    │───>│  Local vLLM        │  │
│  │  File Watcher Daemon   │    │  (Hermes/Qwen-35B) │  │
│  └──────────┬─────────────┘    └────────────────────┘  │
│             │ (Kernel-Level OpenShell Sandbox Policy)  │
│             ▼                                          │
│  ┌────────────────────────┐    ┌────────────────────┐  │
│  │  ProtocolClaw          │    │  SafetyClaw        │  │
│  │  (Deviation Sentinel)  │    │  (FDA 3500A Scribe)│  │
│  └──────────┬─────────────┘    └─────────┬──────────┘  │
└─────────────┼────────────────────────────┼─────────────┘
              │                            │
              ▼                            ▼
┌────────────────────────────────────────────────────────┐
│       1-Click Clinician Review & Sign-Off Gateway      │
│       (Cryptographically Logged 21 CFR Part 11 Audit)  │
└────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```text
app.py                                # Interactive Streamlit pitch demo UI
nemoclaw-rag.toml                     # Single source of truth for RAG & agent config
requirements.txt                      # Python dependencies (pymongo, pyyaml, streamlit)

agents/
├── __init__.py
├── protocol_claw.py                  # Protocol deviation sentinel & con-med checker
└── safety_claw.py                    # CTCAE grader, MedDRA mapper & FDA 3500A drafter

daemon/
├── __init__.py
└── watcher.py                        # Always-on OpenClaw background file watcher

configs/
├── clinical/
│   ├── protocol_rules.yaml           # Machine-readable protocol visit windows & rules
│   └── meddra_mini.json              # Official MedDRA v27.0 Preferred Terms dictionary
├── openshell/
│   ├── careclaw_policy.yaml          # Kernel sandbox policy (zero external cloud egress)
│   └── policy-notes.md
├── hermes/                           # Hermes harness config sketches
└── openclaw/                         # OpenClaw harness config sketches

corpus/
├── protocol/
│   └── onco_2026_x88.md              # Full clinical trial protocol (ONCO-2026-X88)
└── fixtures/
    ├── neon-beacon.md                # RAG smoke test fixture
    ├── patient_004_visit_note.txt    # Seeded messy EHR progress note
    └── patient_004_labs.json         # Seeded CMP chemistry panel (Grade 3 ALT)

rag/
├── agent_tools.py                    # Structured RAG function tool for agent runtimes
├── chunk.py                          # Markdown chunking with boundary safety
├── config.py                         # TOML & environment configuration loader
├── env.py                            # Stdlib .env loader
├── pipeline.py                       # Ingest, retrieve, extractive & model generation
└── store.py                          # MongoDB text-index store and query engine

incoming_records/                     # Monitored directory for live drop ingestion
audit_logs/                           # Append-only 21 CFR Part 11 audit records
tests/                                # Unit test suite (RAG core + CareClaw agents)
```

---

## Hackathon Pitch & Business Value

* **Phase 1 (Dose Escalation)**: Maps labs against protocol DLT criteria instantly, shortening dose-escalation pauses by weeks.
* **Phase 2 (Proof-of-Concept)**: Catches prohibited drug interactions in real time, protecting proof-of-concept data from pharmacokinetic confounders.
* **Phase 3 (Confirmatory Trials)**: Automates thousands of FDA 3500A / CIOMS I narratives and prevents front-end EDC data queries, saving **\$1M+ in direct operational overhead per study**.
* **Zero Cloud Egress**: 100% compliant with HIPAA, EU GDPR, and FDA 21 CFR Part 11.
