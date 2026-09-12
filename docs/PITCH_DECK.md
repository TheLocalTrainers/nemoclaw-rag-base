# CareClaw: Sovereign Clinical Trial & Safety Copilot
## Dell x NVIDIA AI Hackathon Pitch Deck (Cornell University)
**Hardware:** Dell Pro Max Workstation with NVIDIA GB10  
**Stack:** NemoClaw + OpenClaw + OpenShell + Local vLLM Inference  
**Presentation Time:** 5 Minutes (3 Min Demo, 2 Min Q&A)

---

## Slide 1: Title & The Core Thesis
* **Headline:** CareClaw: Sovereign Administrative Copilot for Clinical Trials
* **Sub-headline:** Eliminating the Front-End Data Reconciliation Lag in Clinical Operations — 100% Locally on the Dell GB10.
* **Visual Elements:**
  * Left: Dell Pro Max Workstation badged with NVIDIA GB10 logo.
  * Center: Split graphic showing messy EHR clinical progress notes & lab PDFs flowing into an air-gapped Dell box, producing zero-draft FDA 3500A forms.
  * Footer Badges: `100% Local Inference` | `Zero Cloud Egress` | `21 CFR Part 11 Compliant HITL`
* **Speaker Script (0:00 – 0:35):**
  > "Clinical trials are the engine of modern medicine, but behind every breakthrough is an operational bottleneck: manual human data reconciliation. Despite digital EDC systems and risk-based monitoring, coordinators and data managers still spend hundreds of hours manually cross-checking messy doctor notes and lab slips against 100-page protocol rules.
  > 
  > That administrative lag causes two major failures: Important Protocol Deviations are caught weeks late, and adverse event reporting is delayed.
  > 
  > We built **CareClaw** on the **Dell Pro Max with NVIDIA GB10**—an always-on, air-gapped administrative copilot that catches protocol deviations in real time and pre-drafts FDA safety filings in ten seconds flat, with zero patient data ever leaving the building."

---

## Slide 2: The Enterprise Pain: Front-End Manual Friction
* **Headline:** The Problem: Modern Trials with a Manual Front-End Bottleneck
* **Visual Layout (3 Callout Cards):**
  * **Card 1: EDC Query Churn (\$120–\$160 per query)**  
    * 15%–20% of manually transcribed records trigger data discrepancy queries.
    * In a Phase 3 study with 12,000 queries, sponsors burn **\$1.5M+** on administrative back-and-forth between sites and data managers.
  * **Card 2: Important Protocol Deviations (IPDs)**  
    * Out-of-window lab visits and unrecorded prohibited concomitant medications invalidate primary endpoint data for 8%–10% of patients.
    * Replacing or re-consenting a non-evaluable patient costs **\$45,000–\$65,000**.
  * **Card 3: Adverse Event Narrative Overhead**  
    * Under 21 CFR 312.64 and 312.32, compiling and coding an Individual Case Safety Report (ICSR) takes 4–6 hours of medical writer time, costing **\$180–\$380 per case**.
* **Footnote:** Sources: *Tufts CSDD (2023/2024)*, *Deloitte Life Sciences (2023)*, *Medidata Benchmarks (2024)*.
* **Speaker Script (0:35 – 1:05):**
  > "Industry adoption of Risk-Based Monitoring (RBQM) is over 90%, but data extraction at the clinical site remains deeply manual. When a patient takes an unapproved over-the-counter drug or misses a biomarker visit window, that error sits unnoticed in unstructured chart notes until centralized monitoring reconciles it weeks later. 
  > 
  > At that point, the primary endpoint data is compromised, queries fly back and forth, and safety reporting clocks are compressed. We don't need another generic dashboard—we need an autonomous front-end sentinel."

---

## Slide 3: The Architecture: Dell GB10 + NemoClaw + OpenShell
* **Headline:** Air-Gapped, Always-On Local Intelligence
* **Architecture Flowchart:**
  ```
  [Incoming De-identified Drop: EHR Notes + Lab JSONs]
                           │
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │               Dell Pro Max with NVIDIA GB10             │
  │                                                         │
  │  ┌─────────────────────────┐   ┌─────────────────────┐  │
  │  │  OpenClaw Always-On     │──>│  Local vLLM         │  │
  │  │  File Watcher Daemon    │   │  (Hermes/Qwen-35B)  │  │
  │  └───────────┬─────────────┘   └─────────────────────┘  │
  │              │ (Sandboxed Execution via OpenShell)      │
  │              ▼                                          │
  │  ┌─────────────────────────┐   ┌─────────────────────┐  │
  │  │  ProtocolClaw           │   │  SafetyClaw         │  │
  │  │  (Deviation Sentinel)   │   │  (FDA 3500A Scribe) │  │
  │  └───────────┬─────────────┘   └──────────┬──────────┘  │
  └──────────────┼────────────────────────────┼─────────────┘
                 │                            │
                 ▼                            ▼
  ┌─────────────────────────────────────────────────────────┐
  │       1-Click Clinician Review & Sign-off Gateway       │
  │       (Cryptographically Logged 21 CFR Part 11 Audit)   │
  └─────────────────────────────────────────────────────────┘
  ```
* **Key Technical Pillars:**
  * **OpenClaw:** Always-on system service watching the research folder drop; triggers within 250ms without human prompt.
  * **OpenShell Sandbox:** Enforces `network: isolated` (strictly zero external network egress) and read-only access to source files.
  * **NemoClaw Guardrails:** Enforces factual grounding to source text and constrains MedDRA output strictly to official dictionary codes.
  * **NVIDIA GB10 Unified Memory:** Holds 100-page trial protocol permanently in KV cache via prefix caching for sub-second tool execution.
* **Speaker Script (1:05 – 1:35):**
  > "Why Dell Pro Max with NVIDIA GB10? Clinical protocols are 100-page documents with complex rules. Consumer GPUs run out of memory when holding a 60,000-token protocol in KV cache alongside multi-agent state. The GB10’s unified memory holds the entire protocol permanently resident in memory for instant execution.
  > 
  > Furthermore, HIPAA and GDPR strictly prohibit sending identifiable patient notes over public cloud APIs. With NVIDIA OpenShell, we isolate the agent at the kernel level: zero outbound internet egress. All inference runs locally via vLLM."

---

## Slide 4: LIVE DEMO (The 3-Minute Live Action)
* **Headline:** Live Demonstration: Zero-Draft Automation in Action
* **On-Screen Live Split Screen:**
  * **Left Window (Terminal / OpenClaw Daemon):**
    * Live log of OpenClaw file watcher.
    * Drop `patient_004_visit_note.txt` (messy doctor note: delayed C1D14 visit occurring on Day 19; patient started oral ketoconazole; reports upper abdominal discomfort) and `labs_day19.json` (ALT 265 U/L).
    * Show instant execution: `ProtocolClaw` matches rules in 1.8s; `SafetyClaw` drafts narrative in 3.2s.
  * **Right Window (CareClaw Clinician UI):**
    * **Alert Card 1 (Important Protocol Deviation):**
      * 🔴 *Violation:* Visit C1D14 completed on Day 19 (Window: Day 14 $\pm$ 2 days. 3 days late).
      * 🔴 *Prohibited Con-Med:* Ketoconazole detected (Violates Protocol Section 5.2: Potent CYP3A4 Inhibitors).
    * **Alert Card 2 (Pre-Drafted FDA Form 3500A / CIOMS I):**
      * Auto-graded: ALT $>5\times$ ULN (CTCAE Grade 3).
      * MedDRA Preferred Terms mapped: `Alanine aminotransferase increased` (Code 10001551) & `Abdominal pain upper` (Code 10000087).
      * Chronological narrative pre-written with dosing timeline.
    * **The Action:** Single click on **[Approve Deviation & Sign 3500A]** $\rightarrow$ produces a cryptographically hashed 21 CFR Part 11 audit log entry.
* **Speaker Script (1:35 – 3:35):**
  > *(Proceeds with live demo as detailed above, pointing out local inference speed and OpenShell policy enforcement).*

---

## Slide 5: Value Across the Entire Clinical Lifecycle
* **Headline:** Tailored Value Across Every Phase of Development
* **Visual Matrix:**

| Phase | Core Objective & Pain Point | CareClaw Agent Role | Measurable Impact |
| :--- | :--- | :--- | :--- |
| **Phase 1** *(n = 20–80)* | **Dose Escalation Velocity:** Dosing paused between cohorts waiting on DLT evaluations. | `DLTSentinelAgent`: Compares daily labs against protocol DLT criteria instantly. | **Saves 2–3 weeks** per dose-escalation cohort pause. |
| **Phase 2** *(n = 100–300)* | **Data Integrity:** Concomitant drugs confounding proof-of-concept endpoints. | `ConMedGuardAgent`: Scans notes for newly prescribed prohibited con-meds. | **Protects Go/No-Go data** from pharmacokinetic confounders. |
| **Phase 3** *(n = 800–2,500)* | **Massive Volume & Scale:** 5,000+ AEs and 12,000+ manual EDC queries. | `MedWatchScribeAgent` & `EDCPreEntryAudit`: Auto-drafts 3500A; query prevention. | **\$750k–\$1.45M direct savings** per study; shaves 1 mo off DB Lock. |

* **Speaker Script (3:35 – 4:05):**
  > "CareClaw isn't a single-phase tool; it adapts to the clinical lifecycle. In Phase 1, it delivers velocity—compressing cohort review pauses by weeks. In Phase 2, it protects data integrity—stopping prohibited concomitant drugs from ruining proof-of-concept signals. In Phase 3, it delivers raw labor substitution—automating thousands of regulatory filings across global hospital sites."

---

## Slide 6: Grounded Financial ROI (Phase 3 Economics)
* **Headline:** Realistic, Line-Item Financial Savings
* **Visual Breakdown (Per Pivotal Phase 3 Trial):**
  * **1. Adverse Event Scribing & MedDRA Mapping: \$600,000 Savings**  
    * 5,000 recorded cases $\times$ \$120 net labor reduction per case (Deloitte benchmark: \$180–\$380 fully loaded baseline).
  * **2. EDC Data Query Prevention: \$240,000 Savings**  
    * 2,000 avoidable queries eliminated at the front-end $\times$ \$120 per query resolution cost (Medidata benchmark).
  * **3. Mitigating Non-Evaluable Primary Endpoint Data: \$240,000 Savings**  
    * Protecting just 6 patients from avoidable IPD disqualification $\times$ \$40,000 replacement cost.
  * **TOTAL SAVINGS PER TRIAL:** **\$1,080,000** (Direct bottom-line operational savings).
  * **Portfolio Multiplier:** A sponsor running 8 active trials saves **\$8.6 Million annually**.
* **Speaker Script (4:05 – 4:35):**
  > "These aren't hypothetical numbers. In an average Phase 3 trial, case intake and data queries consume millions. By reducing narrative drafting time by 50% and preventing 2,000 front-end data queries, CareClaw delivers over \$1 Million in direct operational savings per pivotal study."

---

## Slide 7: Regulatory Defense & 21 CFR Part 11 Compliance
* **Headline:** Engineered for Clinical & Regulatory Scrutiny
* **Visual Callout Boxes:**
  * **No Clinical Prediction:** The model never decides whether a drug caused an adverse event. Causality and expectedness remain 100% with the Principal Investigator.
  * **Zero MedDRA Hallucination:** NeMo Guardrails constrained decoding restricts token generation strictly to valid MedDRA dictionary codes.
  * **Audit-Ready HITL:** Every accepted deviation and drafted 3500A narrative requires an explicit, authenticated clinician sign-off with an SHA-256 audit record.
  * **GAMP 5 Validation:** Fixed local weights on Dell hardware guarantee deterministic, auditable outputs—eliminating the silent API drifts of public clouds.
* **Speaker Script (4:35 – 4:55):**
  > "We did not build an AI that tries to out-diagnose physicians. Causality and clinical judgment remain 100% with the licensed investigator. We automated the mechanical, error-prone administrative paperwork. With OpenShell sandboxing, NeMo Guardrails, and cryptographic audit trails, CareClaw is designed to withstand an FDA GCP inspection on day one."

---

## Slide 8: The Ask & Competitive Advantage
* **Headline:** The Dell + NVIDIA Sovereign Enterprise Edge
* **Summary Table:**
  * **Dell Pro Max:** The trusted enterprise on-prem hardware appliance for hospital research enclaves.
  * **NVIDIA GB10:** Massive unified memory for large protocol prefix caching and real-time local inference.
  * **NemoClaw + OpenClaw + OpenShell:** The zero-trust, policy-enforced agent runtime for regulated industries.
* **Concluding Call to Action:**  
  * *"CareClaw: Sovereign, secure, always-on clinical trial operations."*
* **Speaker Script (4:55 – 5:00):**
  > "CareClaw turns days of administrative friction into seconds of zero-draft intelligence. Built for Dell. Accelerated by NVIDIA. Ready for the clinic. Thank you!"

---

## Appendix: Rapid-Fire Q&A Defense (For the 2-Min Live Q&A)

### Q1: "Why can't you just use OpenAI or Claude with an enterprise BAA?"
* **Answer:** *"Three reasons: First, cross-border data sovereignty under EU GDPR and China PIPL prohibits exporting clinical trial health records out of regional jurisdictions. Second, cloud APIs change model weights and hyperparameter defaults without notice, breaking FDA GAMP 5 software validation. Third, the Dell GB10 with vLLM prefix caching holds the 100-page protocol permanently in memory, delivering sub-second response times with zero monthly token billing."*

### Q2: "What happens if the model misses a serious adverse event?"
* **Answer:** *"CareClaw is a secondary administrative sentinel, not a replacement for standard clinical care. It accelerates identification by surfacing potential events the moment a note is typed. Crucially, under 21 CFR 312.64, the Principal Investigator retains sole legal accountability for safety reporting. We reduce their administrative preparation time from six hours to ten minutes."*

### Q3: "How does the agent handle messy, relative time descriptions in notes?"
* **Answer:** *"Physician notes often say 'patient noted fatigue last Tuesday.' During ingestion, OpenClaw anchors all relative time expressions against the note's creation timestamp, calculating the exact offset relative to the patient's Cycle 1 Day 1 date before passing it to the deterministic window rule engine."*
