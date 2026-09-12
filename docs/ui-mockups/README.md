# CareClaw — PI Review UI mockups

Three static, standalone HTML explorations of the Principal Investigator review
experience, offered as **calmer, more readable alternatives** to the current
dense admin dashboard. Each uses the real **PT-004** case (protocol
ONCO-2026-X88, Nexavatinib 200 mg PO daily, Study Day 19) so it reads as real,
and each shows the full picture: patient header, the two protocol deviations,
the two Grade 3 labs, the MedDRA terms, a peek at the FDA 3500A draft, and a
clear **Approve & Sign** action. No backend, no framework — inline CSS, Google
Fonts only, light vanilla JS in direction C for expand/collapse.

Open any file directly in a browser to review it. These live only under
`docs/ui-mockups/`; the live app (`web/`, `store/`, agents) is untouched.

---

## A — Calm Clinical (`A-calm-clinical.html`)
**The idea.** The opposite of a dashboard: one long, editorial reading column
(~820px) with generous whitespace, a 16px base and a real typographic scale.
Findings are quiet numbered *sections* with a soft severity chip, not busy
cards. Type pairs **Fraunces** (a warm serif) for display with **Public Sans**
for body and **JetBrains Mono** for IDs, hashes and the 3500A block; the palette
is a warm off-white paper with a single muted-sage accent and desaturated
amber/red for severity — deliberately away from the current indigo look. A
translucent sticky footer keeps *Approve & Sign* in reach without shouting.
**Best for.** PIs who want to read the whole case top-to-bottom, unhurried, like
a well-set document. **Trade-off.** It optimizes for calm reading over speed —
you scroll through everything rather than triaging, and it shows a single case
rather than a multi-case queue.

## B — Focused Triage (`B-focused-triage.html`)
**The idea.** "Inbox zero for safety review." A dark patient banner anchors the
top, a progress rail shows the findings as steps, and the PI works **one big
alert block at a time** with previous/next controls — each finding gets a full,
scannable stage with its own key-value facts. Remaining findings sit behind a
single "preview the rest" disclosure so the page is complete at rest without
being an alert wall. A **persistent sign dock** with a progress ring stays
pinned so *Approve & Sign* is always one obvious click away. Type is
**Space Grotesk** display + **IBM Plex Sans**/**Mono**; the palette is cool
slate with a focused blue accent and strong semantic severity. **Best for.**
High-volume reviewing where the PI wants momentum and a clear "how many left"
signal. **Trade-off.** The stepper is the most interaction-heavy of the three
and the least glanceable as a whole — great for working *through* a case, less so
for taking it in all at once (and it leans on JS/motion in a real build).

## C — Plain-Language / Summary-First (`C-plain-language.html`)
**The idea.** Leads with a plain-English verdict — *"2 issues need your
attention before you can sign"* — plus an at-a-glance checklist, then uses
**progressive disclosure**: every item states the problem in low-jargon terms
("taking a medicine the trial doesn't allow", "liver enzymes are severely
elevated") and expands on demand to reveal the clinical detail (ketoconazole /
CYP3A4, §5.2.1, 5.9× ULN, MedDRA codes). Built for accessibility and speed:
**Atkinson Hyperlegible** body type, high-contrast AA colors, large hit targets,
a deep-teal accent, and an "Expand all details" toggle (the only JS). **Best
for.** Fast scanning and for non-specialist or cross-functional readers who need
the gist first with clinical rigor a click away. **Trade-off.** Plain-language
framing risks feeling *too* simplified to some specialists, and key detail is
hidden until expanded — a deliberate bet that summary-first beats
everything-at-once.

---

### Notes for whoever picks a direction
- All three are light-mode, don't scroll sideways, and stay readable down to
  phone widths.
- Severity stays legible at a glance everywhere (a calm chip/stripe) without the
  page becoming a wall of red.
- The causality/action fields are shown **blank on purpose** in every mockup —
  CareClaw drafts, the PI decides.
- Fonts are the main lever if you want to blend directions: e.g. keep B's
  stepper flow but adopt A's serif calm, or apply C's plain-language labels on
  top of A's single column.
