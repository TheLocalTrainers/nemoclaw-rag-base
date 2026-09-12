"""CareClaw clinician review gateway (Streamlit).

Two modes:
1. Review Queue — cases enqueued by the OpenClaw daemon (hackathon live path)
2. Manual Simulate — paste a note / labs and run agents in-process (fallback)
"""

from __future__ import annotations

import streamlit as st

from agents.protocol_claw import ProtocolClaw
from agents.safety_claw import SafetyClaw
from store.careclaw_store import (
    EVENT_DISMISSED,
    EVENT_SIGNED,
    STATUS_DISMISSED,
    STATUS_SIGNED,
    CareClawStore,
)


@st.cache_resource
def get_store() -> CareClawStore:
    """Shared MongoDB-backed store — the single source of truth (fails fast)."""
    return CareClawStore()


DEFAULT_NOTE = """CLINICAL OUTPATIENT PROGRESS NOTE
Patient ID: PT-004 | Date: 2026-09-08 | Study Protocol: ONCO-2026-X88
Patient presents today for delayed Cycle 1 Day 14 visit on Study Day 19. 
Patient was traveling out of state and missed the scheduled Day 14 window.
Patient reports 4 days of right-upper-quadrant abdominal tenderness and fatigue.
Medication Reconciliation: Patient started oral ketoconazole 4 days ago for a fungal infection."""


def load_pending_cases() -> list[dict]:
    return get_store().load_pending_cases()


def render_case_outputs(case: dict) -> None:
    deviations = case.get("deviations") or []
    lab_findings = case.get("lab_findings") or []
    draft = case.get("draft_narrative") or ""

    st.markdown("### 🚨 ProtocolClaw — Deviation Sentinel")
    if deviations:
        for dev in deviations:
            severity_color = "🔴" if dev.get("severity") == "CRITICAL" else "🟠"
            st.error(
                f"{severity_color} **{dev['category']} ({dev.get('severity', 'MAJOR')})**\n\n"
                f"**Citation:** {dev.get('protocol_section', 'Protocol Rule')}\n\n"
                f"{dev['details']}\n\n"
                f"**Action Required:** *{dev.get('action_required', '')}*"
            )
    else:
        st.success("✓ No protocol deviations detected.")

    st.markdown("### 📋 SafetyClaw — FDA MedWatch 3500A Scribe")
    for lab in lab_findings:
        if lab.get("is_severe"):
            st.warning(
                f"⚠️ **{lab['analyte']}**: {lab['value']} ({lab['uln_multiple']}) — "
                f"**{lab['ctcae_grade']}**\n\n*Protocol Rule:* {lab['protocol_action']}"
            )
        else:
            st.info(f"{lab['analyte']}: {lab['value']} ({lab['uln_multiple']}) — {lab['ctcae_grade']}")

    symptoms = case.get("symptoms_mapped") or []
    if symptoms:
        st.caption(
            "MedDRA mapped: "
            + ", ".join(f"{s['meddra_pt']} ({s['meddra_code']})" for s in symptoms)
        )

    with st.expander("📄 Pre-Drafted FDA Form 3500A / CIOMS I Narrative", expanded=True):
        st.text_area("Narrative (zero-draft for PI adjudication):", value=draft, height=260)


def sign_case(case: dict, clinician_id: str = "PI-DR-VANCE-MD") -> dict:
    safety = SafetyClaw()
    narrative = case.get("draft_narrative") or ""
    audit = safety.generate_part11_audit_record(narrative, clinician_id=clinician_id)
    store = get_store()
    if case.get("case_id"):
        store.set_case_status(case["case_id"], STATUS_SIGNED)
    store.append_event(
        {
            "event": EVENT_SIGNED,
            "case_id": case.get("case_id"),
            "status": audit["status"],
            "patient_meta": case.get("patient_meta"),
            "deviations": case.get("deviations"),
            "lab_findings": case.get("lab_findings"),
            "draft_narrative": narrative,
            "audit_record": audit,
        }
    )
    return audit


st.set_page_config(
    page_title="CareClaw | Dell x NVIDIA",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .badge-local {
        background-color: #065f46; color: #6ee7b7;
        padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;
    }
    .badge-sandbox {
        background-color: #1e3a8a; color: #93c5fd;
        padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🛡️ CareClaw: Sovereign Clinical Trial Copilot")
st.markdown(
    '<span class="badge-local">● 100% LOCAL ON GB10</span> &nbsp; '
    '<span class="badge-sandbox">● OPENSHELL POLICY READY</span> &nbsp; '
    '<span class="badge-local">● 21 CFR PART 11 AUDIT READY</span>',
    unsafe_allow_html=True,
)
st.caption("Dell Pro Max Workstation with NVIDIA GB10 | NemoClaw + OpenClaw + OpenShell")

with st.sidebar:
    st.header("📋 Trial Protocol Specification")
    st.markdown("**Protocol ID:** `ONCO-2026-X88`")
    st.markdown("**Drug:** Nexavatinib (200mg PO daily)")
    st.markdown("**Indication:** Refractory mCRC")
    st.divider()
    st.subheader("Visit Windows (Section 8.1)")
    st.markdown("- **C1D14:** Day 14 ± 2 days (*Days 12–16*)")
    st.markdown("- **C1D28:** Day 28 ± 2 days (*Days 26–30*)")
    st.subheader("Prohibited Con-Meds (Section 5.2)")
    st.markdown("- **CYP3A4 Inhibitors:** Ketoconazole, Itraconazole, Clarithromycin")
    st.markdown("- **Anticoagulants:** Warfarin, High-dose DOACs")
    st.divider()
    st.markdown("🔒 **OpenShell Policy:** `network: isolated`")
    mode = st.radio(
        "Gateway mode",
        ["Review Queue (daemon)", "Manual Simulate"],
        index=0,
        help="Hackathon live path uses Review Queue fed by `python -m daemon.watcher`.",
    )

if mode.startswith("Review Queue"):
    st.subheader("📥 Principal Investigator Review Inbox")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("🔄 Refresh queue", use_container_width=True):
            st.rerun()
    pending = load_pending_cases()
    st.caption(f"Pending cases: **{len(pending)}** · source `MongoDB careclaw.cases`")

    if not pending:
        st.info(
            "No cases waiting. Start the daemon (`python -m daemon.watcher`), then run "
            "`./scripts/hackathon_demo_drop.sh` to drop PT-004 fixtures into `incoming_records/`."
        )
    else:
        labels = [
            f"{c.get('case_id', 'UNKNOWN')} · "
            f"{(c.get('patient_meta') or {}).get('patient_id', '?')} · "
            f"{len(c.get('deviations') or [])} deviation(s)"
            for c in pending
        ]
        selected_label = st.selectbox("Open case", labels)
        case = pending[labels.index(selected_label)]

        meta = case.get("patient_meta") or {}
        st.markdown(
            f"**Patient** `{meta.get('patient_id')}` · "
            f"**Study Day** `{meta.get('study_day')}` · "
            f"**Source** `{case.get('source_file')}` · "
            f"**Status** `{case.get('status')}`"
        )
        if case.get("note_excerpt"):
            with st.expander("Source note excerpt"):
                st.text(case["note_excerpt"])

        render_case_outputs(case)

        st.divider()
        st.markdown("#### ✍️ Principal Investigator Adjudication Gateway")
        c1, c2 = st.columns(2)
        with c1:
            approve = st.button(
                "✓ Approve Deviation & Sign 3500A (21 CFR Part 11)",
                type="primary",
                use_container_width=True,
            )
        with c2:
            dismiss = st.button("Dismiss from queue", use_container_width=True)

        if approve:
            audit = sign_case(case)  # sets status SIGNED in MongoDB + logs event
            st.success(
                f"**Electronic Record Signed & Locked**\n\n"
                f"- **Audit ID:** `{audit['audit_id']}`\n"
                f"- **SHA-256 Signature:** `{audit['sha256_signature']}`\n"
                f"- **Signer:** `{audit['clinician_id']}`\n"
                f"- **Timestamp (UTC):** `{audit['timestamp_utc']}`"
            )
            st.balloons()
        elif dismiss:
            store = get_store()
            if case.get("case_id"):
                store.set_case_status(case["case_id"], STATUS_DISMISSED)
            store.append_event({"event": EVENT_DISMISSED, "case_id": case.get("case_id")})
            st.warning("Case dismissed from PI queue.")
            st.rerun()

else:
    col_input, col_output = st.columns([1, 1], gap="large")
    with col_input:
        st.subheader("📥 Incoming Record Drop (Simulated EHR)")
        note_text = st.text_area("Physician / Nurse Clinical Progress Note:", value=DEFAULT_NOTE, height=220)
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
            deviations = protocol_claw.audit_record(note_text, patient_meta)
            lab_findings = safety_claw.evaluate_lab_toxicity(mock_lab_data)
            symptoms = safety_claw.extract_meddra_symptoms(note_text)
            draft_3500a = safety_claw.draft_fda_3500a_narrative(
                patient_meta, note_text, lab_findings, symptoms
            )
            case = {
                "case_id": "CASE-MANUAL-PT-004",
                "patient_meta": patient_meta,
                "deviations": deviations,
                "lab_findings": lab_findings,
                "symptoms_mapped": symptoms,
                "draft_narrative": draft_3500a,
            }
            render_case_outputs(case)
            st.divider()
            st.markdown("#### ✍️ Principal Investigator Adjudication Gateway")
            if st.button("✓ 1-Click Authenticate & Electronically Sign (21 CFR Part 11)", type="secondary"):
                audit = sign_case(case)
                st.success(
                    f"**Electronic Record Signed & Locked**\n\n"
                    f"- **Audit ID:** `{audit['audit_id']}`\n"
                    f"- **SHA-256:** `{audit['sha256_signature']}`"
                )
        else:
            st.info("Click **Process** for the offline fallback path, or switch to **Review Queue** for the live daemon demo.")
