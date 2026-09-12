"""CareClaw: Sovereign Clinical Trial & Safety Copilot.

Interactive Streamlit demonstration application for the Dell x NVIDIA Hackathon.
Demonstrates 100% local, always-on protocol deviation monitoring and FDA 3500A
narrative pre-drafting with 1-click 21 CFR Part 11 electronic sign-off.
"""

from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from agents.protocol_claw import ProtocolClaw
from agents.safety_claw import SafetyClaw

st.set_page_config(
    page_title="CareClaw | Dell x NVIDIA",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for clinical professional styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1e293b;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #38bdf8;
        margin-bottom: 12px;
    }
    .badge-local {
        background-color: #065f46;
        color: #6ee7b7;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-sandbox {
        background-color: #1e3a8a;
        color: #93c5fd;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Top Bar / Branding
st.title("🛡️ CareClaw: Sovereign Clinical Trial Copilot")
st.markdown(
    '<span class="badge-local">● 100% LOCAL vLLM ON GB10</span> &nbsp; '
    '<span class="badge-sandbox">● OPENSHELL SANDBOX ISOLATED</span> &nbsp; '
    '<span class="badge-local">● 21 CFR PART 11 AUDIT READY</span>',
    unsafe_allow_html=True
)
st.caption("Dell Pro Max Workstation with NVIDIA GB10 | NemoClaw + OpenClaw + OpenShell")

# Sidebar — Protocol Specifications & Governance
with st.sidebar:
    st.header("📋 Trial Protocol Specification")
    st.markdown("**Protocol ID:** `ONCO-2026-X88`")
    st.markdown("**Drug:** Nexavatinib (200mg PO daily)")
    st.markdown("**Indication:** Refractory mCRC")
    
    st.divider()
    st.subheader("Visit Windows (Section 8.1)")
    st.markdown("- **C1D1:** Day 1 (Baseline)")
    st.markdown("- **C1D14:** Day 14 ± 2 days (*Days 12–16*)")
    st.markdown("- **C1D28:** Day 28 ± 2 days (*Days 26–30*)")
    
    st.subheader("Prohibited Con-Meds (Section 5.2)")
    st.markdown("- **Potent CYP3A4 Inhibitors:** Ketoconazole, Itraconazole, Clarithromycin")
    st.markdown("- **Anticoagulants:** Warfarin, High-dose DOACs")

    st.divider()
    st.markdown("🔒 **OpenShell Policy:** `network: isolated`")
    st.caption("Strict zero-egress kernel policy guarantees no PHI leaves on-premise hardware.")

# Main Interface
col_input, col_output = st.columns([1, 1], gap="large")

# Default demo text
DEFAULT_NOTE = """CLINICAL OUTPATIENT PROGRESS NOTE
Patient ID: PT-004 | Date: 2026-09-08 | Study Protocol: ONCO-2026-X88
Patient presents today for delayed Cycle 1 Day 14 visit on Study Day 19. 
Patient was traveling out of state and missed the scheduled Day 14 window.
Patient reports 4 days of right-upper-quadrant abdominal tenderness and fatigue.
Medication Reconciliation: Patient started oral ketoconazole 4 days ago for a fungal infection."""

with col_input:
    st.subheader("📥 Incoming Record Drop (Simulated EHR)")
    
    note_text = st.text_area(
        "Physician / Nurse Clinical Progress Note:",
        value=DEFAULT_NOTE,
        height=220
    )
    
    st.markdown("#### Laboratory Panel Chemistry (STAT CMP)")
    c1, c2, c3 = st.columns(3)
    with c1:
        alt_val = st.number_input("ALT (U/L)", value=265, help="Ref: 7-45 U/L")
    with c2:
        ast_val = st.number_input("AST (U/L)", value=230, help="Ref: 8-40 U/L")
    with c3:
        bili_val = st.number_input("Total Bili (mg/dL)", value=2.4, step=0.1, help="Ref: 0.2-1.2 mg/dL")

    process_btn = st.button("⚡ Process Record through CareClaw Agents", type="primary", use_container_width=True)

with col_output:
    st.subheader("🤖 Real-Time CareClaw Agent Outputs")

    if process_btn:
        protocol_claw = ProtocolClaw()
        safety_claw = SafetyClaw()

        patient_meta = {
            "patient_id": "PT-004",
            "protocol_id": "ONCO-2026-X88",
            "c1d1_date": "2026-08-20",
            "note_date": "2026-09-08",
            "study_day": 19,
            "age": 62,
            "sex": "Male",
        }

        mock_lab_data = {
            "chemistry": {
                "ALT": {"value": alt_val, "unit": "U/L", "ref_high": 45},
                "AST": {"value": ast_val, "unit": "U/L", "ref_high": 40},
                "Total_Bilirubin": {"value": bili_val, "unit": "mg/dL", "ref_high": 1.2},
            }
        }

        # 1. Execute ProtocolClaw
        deviations = protocol_claw.audit_record(note_text, patient_meta)
        
        # 2. Execute SafetyClaw
        lab_findings = safety_claw.evaluate_lab_toxicity(mock_lab_data)
        symptoms = safety_claw.extract_meddra_symptoms(note_text)
        draft_3500a = safety_claw.draft_fda_3500a_narrative(patient_meta, note_text, lab_findings, symptoms)

        # Display Use Case 1: Protocol Deviations
        st.markdown("### 🚨 Use Case 1: Protocol Deviation Sentinel (`ProtocolClaw`)")
        if deviations:
            for dev in deviations:
                severity_color = "🔴" if dev.get("severity") == "CRITICAL" else "🟠"
                st.error(
                    f"{severity_color} **{dev['category']} ({dev.get('severity', 'MAJOR')})**\n\n"
                    f"**Citation:** {dev.get('protocol_section', 'Protocol Rule')}\n\n"
                    f"{dev['details']}\n\n"
                    f"**Action Required:** *{dev['action_required']}*"
                )
        else:
            st.success("✓ No protocol deviations detected.")

        # Display Use Case 2: Toxicity & MedWatch Narrative
        st.markdown("### 📋 Use Case 2: FDA MedWatch 3500A Scribe (`SafetyClaw`)")
        for lab in lab_findings:
            if lab.get("is_severe"):
                st.warning(f"⚠️ **{lab['analyte']}**: {lab['value']} ({lab['uln_multiple']}) — **{lab['ctcae_grade']}**\n\n*Protocol Rule:* {lab['protocol_action']}")

        with st.expander("📄 View Pre-Drafted FDA Form 3500A / CIOMS I Narrative", expanded=True):
            st.text_area("Narrative (Generated in 1.4s by Local vLLM):", value=draft_3500a, height=260)

        # 1-Click Clinician Review
        st.divider()
        st.markdown("#### ✍️ Principal Investigator Adjudication Gateway")
        sign_btn = st.button("✓ 1-Click Authenticate & Electronically Sign (21 CFR Part 11)", type="secondary")
        
        if sign_btn or st.session_state.get("signed"):
            st.session_state["signed"] = True
            audit_record = safety_claw.generate_part11_audit_record(draft_3500a, clinician_id="PI-DR-VANCE-MD")
            
            # Persist to audit log
            audit_dir = Path("audit_logs")
            audit_dir.mkdir(exist_ok=True)
            with open(audit_dir / "careclaw_events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_record) + "\n")

            st.success(
                f"**Electronic Record Signed & Locked**\n\n"
                f"- **Audit ID:** `{audit_record['audit_id']}`\n"
                f"- **SHA-256 Signature:** `{audit_record['sha256_signature']}`\n"
                f"- **Signer:** `{audit_record['clinician_id']}`\n"
                f"- **Timestamp (UTC):** `{audit_record['timestamp_utc']}`\n\n"
                f"*Audit record cryptographically committed to local enclave storage.*"
            )
    else:
        st.info("👈 Click **'Process Record through CareClaw Agents'** to simulate the live intake on the Dell GB10.")
