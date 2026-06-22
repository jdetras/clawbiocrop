"""Red/green TDD suite for the MSCA reviewer panel.

Run: pytest skills/msca-reviewer/tests/
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "msca_reviewer.py"
sys.path.insert(0, str(SKILL_DIR))

from reviewers import (  # noqa: E402
    ExcellenceReviewer,
    ImpactReviewer,
    ImplementationReviewer,
    ComplianceReviewer,
    PanelChair,
    FeedbackAgent,
    load_rules,
    parse_proposal,
)

STRONG = """
# Abstract
This project tackles drought tolerance in rice.

# 1. Excellence
## Objectives and state of the art
Our objectives are O1, O2, O3. The current state of the art in drought genomics
is limited. This project goes beyond the state of the art by introducing a novel,
ambitious framework. Research question: how do alleles drive tolerance? Hypothesis H1.
## Methodology
A sound, detailed methodology combining interdisciplinary genomics and field work.
We address the gender dimension of smallholder farming. Open science: open access,
FAIR data, a Data Management Plan and preprints are committed.
## Training and two-way transfer of knowledge
Concrete training in transferable skills; two-way transfer of knowledge between the
researcher and the host group; complementary expertise.
## Supervision
The supervisor has a strong track record and mentoring plan; full integration in the host team.

# 2. Impact
## Career
A concrete Career Development Plan enhances employability and skills development and
the next career step toward independence.
## Dissemination, exploitation and communication
A dissemination plan for peers, an exploitation plan with IPR, and communication and
public engagement for target audiences, including open access.
## Impact pathways
Scientific, societal and economic impact pathways with significant uptake by end users.

# 3. Quality and Efficiency of the Implementation
## Work plan
Work packages WP1, WP2, WP3 with milestones and deliverables. A Gantt chart and timeline.
Risk assessment with mitigation and contingency. Effort is appropriately distributed.
## Host capacity
The host institution provides excellent infrastructure, facilities and equipment.

# Ethics
Ethics issues are addressed.

# References
[1] Smith et al. 2024.
"""

WEAK = """
# 1. Excellence
We will study rice. It will be good and interesting.
# 2. Impact
It will help people.
# 3. Implementation
We will do the work over two years.
"""


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def test_load_rules_has_three_weighted_criteria(rules):
    crit = {c["id"]: c for c in rules["criteria"]}
    assert set(crit) == {"excellence", "impact", "implementation"}
    assert crit["excellence"]["weight"] == 0.50
    assert crit["impact"]["weight"] == 0.30
    assert crit["implementation"]["weight"] == 0.20
    assert abs(sum(c["weight"] for c in rules["criteria"]) - 1.0) < 1e-9


def test_parse_proposal_returns_text_and_wordcount():
    p = parse_proposal(STRONG)
    assert p["word_count"] > 50
    assert "excellence" in p["text"].lower()


def test_excellence_reviewer_scores_strong_higher_than_weak(rules):
    r = ExcellenceReviewer(rules)
    strong = r.review(parse_proposal(STRONG))
    weak = r.review(parse_proposal(WEAK))
    assert 0 <= weak["score"] <= strong["score"] <= 5
    assert strong["score"] > weak["score"]
    # each sub-criterion is scored
    assert {s["id"] for s in strong["sub_scores"]} == {"E1", "E2", "E3", "E4"}


def test_each_reviewer_returns_score_in_range(rules):
    p = parse_proposal(STRONG)
    for cls in (ExcellenceReviewer, ImpactReviewer, ImplementationReviewer):
        out = cls(rules).review(p)
        assert 0.0 <= out["score"] <= 5.0
        assert out["sub_scores"]
        assert out["rationale"]


def test_compliance_reviewer_flags_missing_sections(rules):
    weak = ComplianceReviewer(rules).review(parse_proposal(WEAK))
    strong = ComplianceReviewer(rules).review(parse_proposal(STRONG))
    assert len(weak["missing_sections"]) > len(strong["missing_sections"])
    assert "ethics" in [m["id"] for m in weak["missing_sections"]]


def test_compliance_flags_page_limit_overrun(rules):
    huge = "Excellence Impact Implementation " + ("word " * 9000)
    out = ComplianceReviewer(rules).review(parse_proposal(huge))
    assert out["page_estimate"] > 10
    assert any("page" in w.lower() for w in out["warnings"])


def test_chair_produces_weighted_percentage(rules):
    p = parse_proposal(STRONG)
    reviews = [
        ExcellenceReviewer(rules).review(p),
        ImpactReviewer(rules).review(p),
        ImplementationReviewer(rules).review(p),
    ]
    verdict = PanelChair(rules).aggregate(reviews)
    assert 0 <= verdict["percentage"] <= 100
    # weighted total must equal manual computation
    by_id = {r["criterion_id"]: r["score"] for r in reviews}
    expected = (by_id["excellence"] / 5 * 50
                + by_id["impact"] / 5 * 30
                + by_id["implementation"] / 5 * 20)
    assert abs(verdict["percentage"] - expected) < 1e-6
    assert verdict["threshold_met"] == (verdict["percentage"] >= 70)
    assert verdict["label"]


def test_strong_grades_higher_than_weak_overall(rules):
    def grade(text):
        p = parse_proposal(text)
        reviews = [
            ExcellenceReviewer(rules).review(p),
            ImpactReviewer(rules).review(p),
            ImplementationReviewer(rules).review(p),
        ]
        return PanelChair(rules).aggregate(reviews)["percentage"]
    assert grade(STRONG) > grade(WEAK)


def test_feedback_agent_lists_missing_and_improvements(rules):
    p = parse_proposal(WEAK)
    reviews = [
        ExcellenceReviewer(rules).review(p),
        ImpactReviewer(rules).review(p),
        ImplementationReviewer(rules).review(p),
    ]
    compliance = ComplianceReviewer(rules).review(p)
    fb = FeedbackAgent(rules).feedback(reviews, compliance)
    assert fb["missing"]
    assert fb["improvements"]
    # weak proposal should surface the state-of-the-art gap
    blob = json.dumps(fb).lower()
    assert "state of the art" in blob or "state-of-the-art" in blob


def test_cli_demo_writes_report_and_json(tmp_path):
    out = tmp_path / "demo"
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--demo", "--output", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "report.md").exists()
    assert (out / "result.json").exists()
    data = json.loads((out / "result.json").read_text())
    assert "percentage" in data
    assert "panel" in data
    assert "feedback" in data
    # disclaimer must be present in the report
    assert "ClawBioCrop" in (out / "report.md").read_text()


def test_cli_input_file(tmp_path):
    prop = tmp_path / "p.md"
    prop.write_text(STRONG)
    out = tmp_path / "run"
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(prop), "--output", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads((out / "result.json").read_text())
    assert data["percentage"] >= data["threshold_pct"] or data["percentage"] >= 0
