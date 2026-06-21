"""The reviewer agents, compliance checker, chair and feedback agent."""
from __future__ import annotations

from typing import Dict, List

from .base import CriterionReviewer, parse_proposal  # noqa: F401


class ExcellenceReviewer(CriterionReviewer):
    criterion_id = "excellence"
    persona = "Reviewer 1 — Excellence specialist (50%)"


class ImpactReviewer(CriterionReviewer):
    criterion_id = "impact"
    persona = "Reviewer 2 — Impact specialist (30%)"


class ImplementationReviewer(CriterionReviewer):
    criterion_id = "implementation"
    persona = "Reviewer 3 — Implementation specialist (20%)"


CRITERION_REVIEWERS = (ExcellenceReviewer, ImpactReviewer, ImplementationReviewer)


class ComplianceReviewer:
    """Admissibility/formatting gatekeeper — does not score, but flags blockers."""

    persona = "Reviewer 4 — Compliance & admissibility officer"

    def __init__(self, rules: dict):
        self.rules = rules

    def review(self, proposal: Dict) -> Dict:
        lower = proposal["lower"]
        present, missing = [], []
        for sec in self.rules["required_sections_checklist"]:
            if any(k.lower() in lower for k in sec["keywords"]):
                present.append({"id": sec["id"], "name": sec["name"]})
            else:
                missing.append({"id": sec["id"], "name": sec["name"]})

        fmt = self.rules["formatting"]
        page_estimate = round(proposal["word_count"] / fmt["approx_words_per_page"], 1)

        warnings: List[str] = []
        if page_estimate > fmt["part_b1_page_limit"]:
            warnings.append(
                f"Estimated {page_estimate} pages of body text exceeds the "
                f"{fmt['part_b1_page_limit']}-page limit for sections 1-3; evaluators "
                f"disregard overflow. Tighten the text."
            )
        missing_ids = {m["id"] for m in missing}
        for hard in ("ethics", "open_science", "gender_dimension", "references"):
            if hard in missing_ids:
                name = next(m["name"] for m in missing if m["id"] == hard)
                warnings.append(f"Required element appears absent: {name}.")

        return {
            "persona": self.persona,
            "page_estimate": page_estimate,
            "page_limit": fmt["part_b1_page_limit"],
            "present_sections": present,
            "missing_sections": missing,
            "warnings": warnings,
        }


class PanelChair:
    """Aggregates reviewer scores into the official weighted percentage grade."""

    persona = "Panel Chair — consensus & weighted grade"

    def __init__(self, rules: dict):
        self.rules = rules

    def aggregate(self, reviews: List[Dict]) -> Dict:
        breakdown = []
        percentage = 0.0
        for r in reviews:
            contribution = r["score"] / r["max_score"] * (r["weight"] * 100)
            percentage += contribution
            breakdown.append({
                "criterion_id": r["criterion_id"],
                "criterion_name": r["criterion_name"],
                "score": r["score"],
                "weight_pct": round(r["weight"] * 100, 1),
                "weighted_points": round(contribution, 2),
            })
        percentage = round(percentage, 2)
        scoring = self.rules["scoring"]
        label, note = self._interpret(percentage)
        return {
            "percentage": percentage,
            "threshold_pct": scoring["funding_threshold_pct"],
            "competitive_target_pct": scoring["competitive_target_pct"],
            "threshold_met": percentage >= scoring["funding_threshold_pct"],
            "competitive": percentage >= scoring["competitive_target_pct"],
            "label": label,
            "note": note,
            "breakdown": breakdown,
        }

    def _interpret(self, pct: float):
        for band in self.rules["scoring"]["interpretation"]:
            if pct >= band["min_pct"]:
                return band["label"], band["note"]
        return "Below threshold", ""


class FeedbackAgent:
    """Synthesises gaps and a prioritised improvement plan across the panel."""

    persona = "Feedback agent — gap analysis & improvement plan"

    def __init__(self, rules: dict):
        self.rules = rules
        self._weights = {c["id"]: c["weight"] for c in rules["criteria"]}

    def feedback(self, reviews: List[Dict], compliance: Dict) -> Dict:
        missing: List[Dict] = []
        improvements: List[Dict] = []

        # 1. Missing required document sections (from the compliance officer).
        for m in compliance["missing_sections"]:
            missing.append({
                "type": "missing_section",
                "item": m["name"],
                "detail": f"No evidence of '{m['name']}' was found in the proposal.",
            })

        # 2. Under-evidenced sub-criteria become missing items + improvement actions.
        for r in reviews:
            w = self._weights[r["criterion_id"]]
            for sub in r["sub_scores"]:
                gap = round(5 - sub["score"], 2)
                if sub["score"] < 3.0:
                    for el in sub["missing_elements"]:
                        missing.append({
                            "type": "weak_subcriterion",
                            "criterion": r["criterion_name"],
                            "subcriterion": sub["name"],
                            "item": el,
                        })
                if gap > 0:
                    improvements.append({
                        "criterion": r["criterion_name"],
                        "subcriterion": sub["name"],
                        "current_score": sub["score"],
                        "headroom": gap,
                        "weighted_impact": round(gap / 5 * w * 100, 2),
                        "action": self._action(sub),
                    })

        improvements.sort(key=lambda x: x["weighted_impact"], reverse=True)
        for w in compliance["warnings"]:
            improvements.insert(0, {
                "criterion": "Compliance",
                "subcriterion": "Admissibility / formatting",
                "weighted_impact": None,
                "action": w,
            })

        tips = [t["tip"] for t in self.rules["reviewer_tips"]]
        return {
            "persona": self.persona,
            "missing": missing,
            "improvements": improvements,
            "top_priorities": [i for i in improvements if i["weighted_impact"]][:3],
            "reviewer_tips": tips,
        }

    @staticmethod
    def _action(sub: Dict) -> str:
        if sub["missing_elements"]:
            return (f"Strengthen '{sub['name']}': explicitly address "
                    + "; ".join(sub["missing_elements"]) + ".")
        return (f"Deepen '{sub['name']}' — it is present but thin. Add specifics, "
                f"evidence and a clearer link to the evaluation sub-criterion.")
