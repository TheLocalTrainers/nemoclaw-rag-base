"""LLM-generated FDA MedWatch 3500A / CIOMS I safety narrative (Qwen on vLLM).

Turns the DETERMINISTIC findings produced by SafetyClaw/ProtocolClaw (CTCAE
grades, MedDRA terms, protocol deviations) into polished clinical-regulatory
prose, WITHOUT inventing facts and WITHOUT asserting causality or final action —
those remain the Principal Investigator's determination.

FAILS SOFT by design: this reuses `web.llm_client`, so any endpoint outage
raises `LLMUnavailable` and the caller falls back to the deterministic zero-draft
`SafetyClaw.draft_fda_3500a_narrative`. The signed 21 CFR Part 11 record is
never blocked on the model being up.

Config (env):
    VLLM_NARRATIVE   default "1"  ("0"/"false"/"no" → skip LLM, use deterministic)
    (plus every VLLM_* knob honored by web.llm_client)
"""

from __future__ import annotations

import os
from typing import Any

from web import llm_client
from web.llm_client import LLMUnavailable  # re-export for callers

__all__ = ["enabled", "generate_3500a_narrative", "LLMUnavailable"]


def enabled() -> bool:
    """Whether LLM narrative generation is turned on (default ON)."""
    return os.environ.get("VLLM_NARRATIVE", "1").lower() not in ("0", "false", "no")


_SYSTEM_PROMPT = (
    "You are CareClaw's regulatory drafting assistant. You write the Section B clinical "
    "narrative of an FDA MedWatch Form 3500A / CIOMS I expedited adverse-event safety report "
    "for an oncology clinical trial. Follow these rules strictly:\n"
    "1. Use ONLY the facts in the CASE DATA below. Never invent or alter labs, values, doses, "
    "dates, drugs, or events. Every number and date in your narrative must match the CASE DATA.\n"
    "2. NEVER assert, imply, grade, or fill in causality (relatedness to the study drug) or the "
    "final action taken with the study drug. Those are the Principal Investigator's determination "
    "and MUST remain blank/pending. If you mention them, state only that they are pending PI "
    "adjudication.\n"
    "3. Write in precise, professional clinical and regulatory prose suitable for an FDA filing. "
    "Present the demographics, the adverse event chronology, the graded laboratory findings, the "
    "coded MedDRA terminology, the protocol deviations, and the protocol-mandated toxicity "
    "management.\n"
    "4. Return ONLY the finished narrative text. No preamble, no commentary, no markdown code "
    "fences, no notes about what you did."
)


def _case_data_block(
    patient_meta: dict[str, Any],
    deviations: list[dict[str, Any]],
    lab_findings: list[dict[str, Any]],
    symptoms: list[dict[str, str]],
    deterministic_draft: str,
) -> str:
    meta = patient_meta or {}
    dev_lines = "\n".join(
        f"  - {d.get('category')} [{d.get('severity')}] "
        f"{d.get('protocol_section', '')}: {d.get('details', '')}"
        for d in (deviations or [])
    ) or "  (none)"
    lab_lines = "\n".join(
        f"  - {l.get('analyte')}: {l.get('value')} ({l.get('uln_multiple')}) — "
        f"{l.get('ctcae_grade')}; MedDRA {l.get('meddra_pt')} ({l.get('meddra_code')}); "
        f"protocol action: {l.get('protocol_action')}"
        for l in (lab_findings or [])
    ) or "  (none)"
    sym_lines = "\n".join(
        f"  - {s.get('meddra_pt')} (MedDRA {s.get('meddra_code')}) "
        f"[reported: '{s.get('reported_term')}']"
        for s in (symptoms or [])
    ) or "  (none)"
    return (
        "CASE DATA (authoritative — do not contradict, do not add facts):\n"
        f"Patient: {meta.get('patient_id')} · {meta.get('age')} yr {meta.get('sex')} · "
        f"Study Day {meta.get('study_day')}\n"
        f"Protocol: {meta.get('protocol_id')} · Investigational drug: "
        "Nexavatinib (NEX-882) 200mg PO daily\n"
        f"C1D1 date: {meta.get('c1d1_date')} · Event assessment date: {meta.get('note_date')}\n"
        f"Protocol deviations:\n{dev_lines}\n"
        f"Graded laboratory findings (CTCAE v5.0):\n{lab_lines}\n"
        f"Coded symptoms (MedDRA):\n{sym_lines}\n\n"
        "DETERMINISTIC ZERO-DRAFT (structure/facts reference — rewrite as flowing prose, "
        "keeping every fact; keep causality and action blank/pending):\n"
        f"{deterministic_draft}"
    )


def generate_3500a_narrative(
    patient_meta: dict[str, Any],
    deviations: list[dict[str, Any]],
    lab_findings: list[dict[str, Any]],
    symptoms: list[dict[str, str]],
    deterministic_draft: str,
    *,
    max_tokens: int = 8192,
    reasoning_effort: str = "medium",
) -> tuple[str, str]:
    """Ask Qwen to write the polished 3500A narrative.

    Returns (narrative_text, model_id). Raises LLMUnavailable when disabled or
    when the endpoint is unreachable / returns empty content, so the caller can
    fall back to the deterministic draft.

    We budget max_tokens generously (reasoning tokens count against it; the old
    3500-token budget with xhigh reasoning ALWAYS returned empty content, so the
    LLM narrative never actually generated) and let ``web.llm_client`` apply the
    clamped thinking-mode temperature/top_p rather than forcing a near-zero temp.
    ``reasoning_effort='medium'`` gives the extra rigor a regulated narrative
    warrants; drop to 'low' for faster turns.
    """
    if not enabled():
        raise LLMUnavailable("narrative generation disabled (VLLM_NARRATIVE=0)")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                _case_data_block(
                    patient_meta, deviations, lab_findings, symptoms, deterministic_draft
                )
                + "\n\nWrite the complete Section B safety narrative now."
            ),
        },
    ]
    # Reasoning model: budget generously so reasoning tokens don't starve content.
    # Temperature/top_p are handled (and clamped off the near-zero floor) centrally
    # in web.llm_client so we don't send temp~0 in thinking mode.
    narrative = llm_client.chat(
        messages, max_tokens=max_tokens, reasoning_effort=reasoning_effort
    )

    # Best-effort model id for telemetry (never fail the narrative on this probe).
    model_id = ""
    try:
        model_id = str(llm_client.status().get("model") or "")
    except Exception:  # noqa: BLE001 - telemetry only
        model_id = ""

    return narrative.strip(), model_id
