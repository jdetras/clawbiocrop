#!/usr/bin/env python3
"""MSCA Reviewer Panel — score an MSCA Postdoctoral Fellowship proposal.

A panel of reviewer agents (Excellence 50%, Impact 30%, Implementation 20%, plus a
Compliance officer) scrutinises a proposal against the official MSCA evaluation
sub-criteria, a Panel Chair computes the weighted percentage grade, and a Feedback
agent returns a prioritised list of what is missing and what to improve.

Usage:
    python skills/msca-reviewer/msca_reviewer.py --input proposal.md --output report_dir
    python skills/msca-reviewer/msca_reviewer.py --demo --output /tmp/msca_demo

ClawBioCrop is a research/educational tool. It is NOT the European Commission, REA,
or an evaluation panel; scores are heuristic estimates only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from reviewers import (  # noqa: E402
    load_rules,
    parse_proposal,
    ExcellenceReviewer,
    ImpactReviewer,
    ImplementationReviewer,
    ComplianceReviewer,
    PanelChair,
    FeedbackAgent,
)

DEMO_PROPOSAL = SKILL_DIR / "examples" / "demo_proposal.md"


def run_panel(text: str, rules: dict) -> dict:
    proposal = parse_proposal(text)
    reviews = [
        ExcellenceReviewer(rules).review(proposal),
        ImpactReviewer(rules).review(proposal),
        ImplementationReviewer(rules).review(proposal),
    ]
    compliance = ComplianceReviewer(rules).review(proposal)
    verdict = PanelChair(rules).aggregate(reviews)
    feedback = FeedbackAgent(rules).feedback(reviews, compliance)

    result = dict(verdict)
    result["word_count"] = proposal["word_count"]
    result["panel"] = reviews
    result["compliance"] = compliance
    result["feedback"] = feedback
    result["disclaimer"] = rules["disclaimer"]
    return result


def render_report(result: dict, rules: dict, source: str) -> str:
    pct = result["percentage"]
    L = []
    L.append("# 🎓 MSCA Postdoctoral Fellowship — Review Panel Report\n")
    L.append(f"**Proposal source:** {source}  ")
    L.append(f"**Scheme:** {rules['scheme']} ({rules['version']})  ")
    L.append(f"**Body-text length:** ~{result['word_count']} words "
             f"(~{result['compliance']['page_estimate']} A4 pages)\n")

    bar = "█" * int(round(pct / 5)) + "░" * (20 - int(round(pct / 5)))
    L.append("## Overall grade\n")
    L.append(f"## **{pct:.1f}%**  `{bar}`\n")
    L.append(f"- **Verdict:** {result['label']} — {result['note']}")
    L.append(f"- **Funding threshold:** {result['threshold_pct']}% "
             f"→ {'✅ met' if result['threshold_met'] else '❌ not met'}")
    L.append(f"- **Competitive target (typical funded proposals):** "
             f"{result['competitive_target_pct']}% "
             f"→ {'✅' if result['competitive'] else '⚠️ below'}\n")

    L.append("### Weighted breakdown\n")
    L.append("| Criterion | Weight | Score /5 | Weighted points |")
    L.append("|---|---|---|---|")
    for b in result["breakdown"]:
        L.append(f"| {b['criterion_name']} | {b['weight_pct']:.0f}% | "
                 f"{b['score']:.2f} | {b['weighted_points']:.1f} |")
    L.append(f"| **Total** |  |  | **{pct:.1f}** |\n")

    L.append("## Reviewer panel scorecards\n")
    for r in result["panel"]:
        L.append(f"### {r['persona']} — {r['score']:.2f}/5\n")
        L.append(f"_{r['rationale']}_\n")
        L.append("| Sub-criterion | Score | Coverage |")
        L.append("|---|---|---|")
        for s in r["sub_scores"]:
            L.append(f"| **{s['id']}** {s['name']} | {s['score']:.2f}/5 | "
                     f"{int(s['coverage']*100)}% |")
        L.append("")

    c = result["compliance"]
    L.append(f"### {c['persona']}\n")
    L.append(f"- Estimated **{c['page_estimate']} pages** vs **{c['page_limit']}-page** "
             f"limit for sections 1-3.")
    if c["missing_sections"]:
        L.append("- **Missing / undetected sections:** "
                 + ", ".join(m["name"] for m in c["missing_sections"]) + ".")
    for w in c["warnings"]:
        L.append(f"- ⚠️ {w}")
    L.append("")

    fb = result["feedback"]
    L.append("## ✍️ Feedback agent — what is missing & what to improve\n")
    if fb["top_priorities"]:
        L.append("### Top priorities (highest weighted gain)\n")
        for i, p in enumerate(fb["top_priorities"], 1):
            imp = f" _(≈+{p['weighted_impact']:.1f} pts available)_" if p["weighted_impact"] else ""
            L.append(f"{i}. **{p['criterion']} → {p['subcriterion']}**{imp}: {p['action']}")
        L.append("")

    if fb["missing"]:
        L.append("### Missing or under-evidenced elements\n")
        seen = set()
        for m in fb["missing"]:
            item = m["item"]
            if item in seen:
                continue
            seen.add(item)
            ctx = f" ({m.get('subcriterion')})" if m.get("subcriterion") else ""
            L.append(f"- {item}{ctx}")
        L.append("")

    L.append("### Full improvement plan\n")
    for i in fb["improvements"]:
        imp = f" _(≈+{i['weighted_impact']:.1f} pts)_" if i.get("weighted_impact") else ""
        L.append(f"- **{i['criterion']} → {i['subcriterion']}**{imp}: {i['action']}")
    L.append("")

    L.append("### Evaluator wisdom (curated MSCA reviewer tips)\n")
    for t in fb["reviewer_tips"]:
        L.append(f"- {t}")
    L.append("")

    L.append("---\n")
    L.append(f"> {result['disclaimer']}\n")
    L.append("> *ClawBioCrop is a research and educational tool for crop genomics and "
             "research-grant support. It is not a breeding-decision system and does not "
             "replace field validation. Confirm findings against primary databases "
             "(IRRI SNP-Seek, RAP-DB, Gramene, Ensembl Plants) before acting on them.*\n")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="MSCA proposal reviewer panel")
    ap.add_argument("--input", help="Proposal file (markdown/txt)")
    ap.add_argument("--demo", action="store_true", help="Run with the built-in demo proposal")
    ap.add_argument("--output", required=True, help="Output report directory")
    args = ap.parse_args(argv)

    if not args.demo and not args.input:
        ap.error("provide --input <file> or --demo")

    if args.demo:
        text = DEMO_PROPOSAL.read_text(encoding="utf-8")
        source = "demo_proposal.md (synthetic)"
    else:
        path = Path(args.input)
        if not path.exists():
            ap.error(f"input not found: {path}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        source = path.name

    rules = load_rules()
    result = run_panel(text, rules)

    out = Path(args.output)
    if out.exists() and any(out.iterdir()):
        print(f"⚠️  Output dir {out} is not empty — overwriting report.md / result.json.")
    out.mkdir(parents=True, exist_ok=True)

    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    report = render_report(result, rules, source)
    (out / "report.md").write_text(report, encoding="utf-8")

    print(f"MSCA panel grade: {result['percentage']:.1f}%  ({result['label']})")
    print(f"  Threshold {result['threshold_pct']}% "
          f"{'met' if result['threshold_met'] else 'NOT met'}; "
          f"report → {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
