"""Shared logic for the MSCA reviewer panel.

Each reviewer agent inspects a parsed proposal and produces a 0-5 score per
sub-criterion, grounded in the official MSCA evaluation-form sub-criteria stored
in ``rules/msca_rules.json``. Scoring is a transparent, reproducible heuristic
(evidence-keyword coverage + required-element detection); the LLM layer adds
qualitative judgement on top, per the SKILL.md contract.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "msca_rules.json"


def load_rules(path: Path | str = RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_proposal(text: str) -> Dict:
    """Normalise a proposal into a structure the reviewers can score."""
    words = re.findall(r"\b\w+\b", text)
    return {
        "text": text,
        "lower": text.lower(),
        "word_count": len(words),
    }


def _coverage(lower_text: str, keywords: List[str]) -> Dict:
    matched = [k for k in keywords if k.lower() in lower_text]
    frac = len(matched) / len(keywords) if keywords else 0.0
    return {"matched": matched, "coverage": round(frac, 3)}


# Fraction of a sub-criterion's evidence keywords that counts as "fully covered".
# The keyword lists deliberately include synonym variants (e.g. "novel"/"novelty",
# "two-way"/"two way") to catch phrasing, so a proposal convincingly addressing the
# concept rarely needs every variant. Matching this fraction of distinct keywords
# saturates the score at 5/5, mirroring how an evaluator judges whether the element
# is *present and convincing* rather than counting words.
SATURATION = 0.65


def _score_from_coverage(coverage: float) -> float:
    """Map keyword coverage (0-1) to an MSCA-style 0-5 score with saturation."""
    effective = min(1.0, coverage / SATURATION) if SATURATION else coverage
    return round(min(5.0, max(0.0, 5.0 * effective)), 2)


class CriterionReviewer:
    """A reviewer agent bound to one award criterion (Excellence/Impact/Impl.)."""

    criterion_id: str = ""
    persona: str = "Panel reviewer"

    def __init__(self, rules: dict):
        self.rules = rules
        self.criterion = next(c for c in rules["criteria"] if c["id"] == self.criterion_id)

    def review(self, proposal: Dict) -> Dict:
        lower = proposal["lower"]
        sub_scores = []
        for sub in self.criterion["sub_criteria"]:
            cov = _coverage(lower, sub["evidence_keywords"])
            score = _score_from_coverage(cov["coverage"])
            missing = self._missing_elements(sub, score)
            sub_scores.append({
                "id": sub["id"],
                "name": sub["name"],
                "text": sub["text"],
                "score": score,
                "coverage": cov["coverage"],
                "matched_keywords": cov["matched"],
                "missing_elements": missing,
            })
        score = round(sum(s["score"] for s in sub_scores) / len(sub_scores), 2)
        strengths = [s["name"] for s in sub_scores if s["score"] >= 3.5]
        weaknesses = [s["name"] for s in sub_scores if s["score"] < 2.5]
        return {
            "criterion_id": self.criterion_id,
            "criterion_name": self.criterion["name"],
            "persona": self.persona,
            "weight": self.criterion["weight"],
            "score": score,
            "max_score": 5,
            "sub_scores": sub_scores,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "rationale": self._rationale(score, strengths, weaknesses),
        }

    @staticmethod
    def _missing_elements(sub: Dict, score: float) -> List[str]:
        # A genuinely weak element (<2.5/5) is reported as missing required elements;
        # a present-but-thin element (>=2.5) gets a "deepen" suggestion instead, so we
        # do not tell an author they are "missing" something they have already covered.
        if score >= 2.5:
            return []
        return list(sub["required_elements"])

    def _rationale(self, score: float, strengths: List[str], weaknesses: List[str]) -> str:
        verdict = ("strong" if score >= 4 else
                   "solid" if score >= 3 else
                   "weak" if score >= 1.5 else "very weak")
        parts = [f"{self.criterion['name']}: {verdict} ({score}/5)."]
        if strengths:
            parts.append("Well-evidenced: " + ", ".join(strengths) + ".")
        if weaknesses:
            parts.append("Under-developed: " + ", ".join(weaknesses) + ".")
        return " ".join(parts)
