# 🎓 MSCA Reviewer Panel

A panel of AI **reviewer agents** that scrutinise a **Marie Skłodowska-Curie Actions
(MSCA) Postdoctoral Fellowship** proposal the way a real evaluation panel would —
scoring it against the official **Excellence (50%) / Impact (30%) / Implementation (20%)**
criteria, producing a **weighted percentage grade**, and returning a prioritised list of
**what is missing and what to improve**.

Part of [ClawBioCrop](https://github.com/jdetras/clawbiocrop). Self-contained: pure Python
standard library, no third-party dependencies.

## The panel

| Agent | Role | Weight |
|---|---|---|
| **Reviewer 1 — Excellence** | Objectives & state of the art, methodology (gender dimension, open science), training & 2-way knowledge transfer, supervision | 50% |
| **Reviewer 2 — Impact** | Career/employability, dissemination/exploitation/communication, magnitude of impact | 30% |
| **Reviewer 3 — Implementation** | Work plan, work packages, Gantt, risks, host capacity | 20% |
| **Reviewer 4 — Compliance** | Page limit, formatting, ethics/open-science/gender presence | admissibility gate |
| **Panel Chair** | Aggregates → weighted % grade + verdict (70% threshold, ~90% competitive) | — |
| **Feedback agent** | Gap analysis + ranked improvement plan | — |

## Quick start

```bash
# Score a proposal draft (Part B sections 1-3, or a full draft, as .md/.txt)
python msca_reviewer.py --input proposal.md --output report_dir

# No file yet? Run the built-in synthetic demo
python msca_reviewer.py --demo --output /tmp/msca_demo
```

Outputs `report.md` (human-readable scorecards + feedback) and `result.json`
(machine-readable scores, weighted breakdown and improvement plan).

```
$ python msca_reviewer.py --demo --output /tmp/msca_demo
MSCA panel grade: 92.6%  (Competitive / fundable)
  Threshold 70% met; report → /tmp/msca_demo/report.md
```

## How it scores

1. Each reviewer scores its sub-criteria 0–5 from the rubric in
   [`rules/msca_rules.json`](rules/msca_rules.json) (evidence detection with a saturation
   point, so a convincingly-addressed element earns full marks).
2. Criterion score = mean of sub-scores; **weighted % = Σ(score/5 × weight × 100)**.
3. Verdict against the **70% funding threshold** and **~90% competitiveness** target.
4. Feedback ranks fixes by the weighted points each can recover.

## Rules base

`rules/msca_rules.json` encodes the official criteria, sub-criteria wording, weights,
thresholds, Part B formatting limits (10 pages, Times New Roman 11pt, ≥15 mm margins) and a
set of curated evaluator tips with sources. Update it each call cycle.

## Tests

```bash
pip install pytest
pytest tests/
```

## Disclaimer

MSCA-Reviewer is a research/educational tool. It is **not** the European Commission, REA, or
an evaluation panel, and its scores are **heuristic estimates only** — not official results.
Always verify against the current MSCA Work Programme, Guide for Applicants and call-specific
evaluation form before submitting. Keep unpublished proposals confidential — they are
processed locally and never uploaded.

## Sources

- [MSCA Postdoctoral Fellowships — REA (how to apply)](https://rea.ec.europa.eu/funding-and-grants/horizon-europe-marie-sklodowska-curie-actions/horizon-europe-msca-how-apply_en)
- [MSCA Postdoctoral Fellowships — European Commission](https://marie-sklodowska-curie-actions.ec.europa.eu/actions/postdoctoral-fellowships)
- [Ten simple rules for a successful MSCA application (PLOS Comput Biol)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9387847/)
