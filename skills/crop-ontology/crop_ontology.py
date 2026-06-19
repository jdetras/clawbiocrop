#!/usr/bin/env python3
"""
crop_ontology.py — Crop & Plant Ontology Lookup (ClawBioCrop Skill)
===================================================================
Search and resolve terms across plant/crop ontologies used in agricultural
genomics: Plant Ontology (PO), Plant Trait Ontology (TO), Plant Experimental
Conditions Ontology (PECO), and the Crop Ontology (CO_xxx, e.g. rice CO_320).
Aggregated by Planteome (https://planteome.org).

Given a free-text query (e.g. "grain yield", "drought", "panicle"), return matching
ontology terms with id, name, definition, ontology source, and parent terms — so
GWAS/QTL traits and phenotypes can be tagged with standard, interoperable identifiers.

Usage:
    python crop_ontology.py --query "grain yield" --output /tmp/ontology
    python crop_ontology.py --term TO:0000396 --output /tmp/ontology
    python crop_ontology.py --demo --output /tmp/ontology_demo

OFFLINE-FIRST: --demo and the bundled term set work without network. Live OLS/Planteome
search is attempted only with --live.

ClawBioCrop is a research and educational tool for crop genomics.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. Ontology terms "
    "are provided for annotation and interoperability; confirm against Planteome / Crop "
    "Ontology before publishing."
)

# Ontology source labels.
ONTOLOGIES = {
    "PO": "Plant Ontology",
    "TO": "Plant Trait Ontology",
    "PECO": "Plant Experimental Conditions Ontology",
    "CO_320": "Crop Ontology (Rice)",
    "CO_321": "Crop Ontology (Wheat)",
    "CO_322": "Crop Ontology (Maize)",
}

# ---------------------------------------------------------------------------
# Bundled term set — a curated offline slice covering common crop GWAS traits,
# anatomy, growth stages, and stress conditions. Ids are real where stable.
# ---------------------------------------------------------------------------
TERMS = [
    {"id": "TO:0000396", "name": "grain yield trait", "ontology": "TO",
     "definition": "A trait related to the mass of grain produced.",
     "parents": ["TO:0000919 yield trait"], "synonyms": ["grain yield"]},
    {"id": "TO:0006001", "name": "panicle number", "ontology": "TO",
     "definition": "The count of panicles per plant.",
     "parents": ["TO:0000919 yield trait"], "synonyms": ["tiller number"]},
    {"id": "TO:0000174", "name": "drought tolerance", "ontology": "TO",
     "definition": "Ability to maintain growth under water-deficit conditions.",
     "parents": ["TO:0000168 abiotic stress trait"], "synonyms": ["water-deficit tolerance"]},
    {"id": "TO:0000598", "name": "submergence tolerance", "ontology": "TO",
     "definition": "Ability to survive complete or partial flooding.",
     "parents": ["TO:0000168 abiotic stress trait"], "synonyms": ["flooding tolerance"]},
    {"id": "TO:0000300", "name": "blast disease resistance", "ontology": "TO",
     "definition": "Resistance to Magnaporthe oryzae infection.",
     "parents": ["TO:0000112 biotic stress trait"], "synonyms": ["rice blast resistance"]},
    {"id": "PO:0009049", "name": "inflorescence", "ontology": "PO",
     "definition": "A shoot system bearing flowers (e.g. the rice panicle).",
     "parents": ["PO:0025497 collective phyllome structure"], "synonyms": ["panicle"]},
    {"id": "PO:0009010", "name": "seed", "ontology": "PO",
     "definition": "A plant structure formed from a fertilised ovule.",
     "parents": ["PO:0009001 fruit"], "synonyms": ["grain", "caryopsis"]},
    {"id": "PO:0007123", "name": "flowering stage", "ontology": "PO",
     "definition": "Reproductive growth stage at which flowers are open.",
     "parents": ["PO:0007033 reproductive growth"], "synonyms": ["anthesis", "heading"]},
    {"id": "PECO:0007199", "name": "drought environment", "ontology": "PECO",
     "definition": "An experimental water-deficit treatment.",
     "parents": ["PECO:0007085 abiotic plant exposure"], "synonyms": ["water-deficit treatment"]},
    {"id": "CO_320:0000040", "name": "Grain weight", "ontology": "CO_320",
     "definition": "Thousand-grain weight measured in grams.",
     "parents": ["CO_320:0000039 Grain quality"], "synonyms": ["1000-grain weight", "TGW"]},
]


# ---------------------------------------------------------------------------
# Search and lookup
# ---------------------------------------------------------------------------

def search_terms(query: str, terms=None, ontology=None):
    """Case-insensitive substring search across name, synonyms, and definition."""
    pool = terms if terms is not None else TERMS
    q = query.lower().strip()
    results = []
    for t in pool:
        if ontology and t["ontology"] != ontology:
            continue
        haystack = " ".join([t["name"], t["definition"], " ".join(t.get("synonyms", []))]).lower()
        if q in haystack:
            score = 0
            if q == t["name"].lower():
                score = 3
            elif q in t["name"].lower() or any(q == s.lower() for s in t.get("synonyms", [])):
                score = 2
            else:
                score = 1
            results.append((score, t))
    results.sort(key=lambda st: (-st[0], st[1]["id"]))
    return [t for _, t in results]


def get_term(term_id: str, terms=None):
    """Exact lookup by ontology id."""
    pool = terms if terms is not None else TERMS
    for t in pool:
        if t["id"] == term_id:
            return t
    return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(query, results, term_id=None):
    lines = ["# Crop & Plant Ontology Report", ""]
    if term_id:
        lines.append(f"**Term**: {term_id}  ")
    if query:
        lines.append(f"**Query**: \"{query}\"  ")
    lines += [
        f"**Matches**: {len(results)}  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Matching terms",
        "",
        "| ID | Name | Ontology | Definition |",
        "|----|------|----------|------------|",
    ]
    for t in results:
        onto = ONTOLOGIES.get(t["ontology"], t["ontology"])
        lines.append(f"| `{t['id']}` | {t['name']} | {onto} | {t['definition']} |")
    if results:
        lines += ["", "## Term detail", ""]
        for t in results:
            lines.append(f"### {t['id']} — {t['name']}")
            lines.append(f"- **Ontology**: {ONTOLOGIES.get(t['ontology'], t['ontology'])}")
            lines.append(f"- **Definition**: {t['definition']}")
            if t.get("synonyms"):
                lines.append(f"- **Synonyms**: {', '.join(t['synonyms'])}")
            if t.get("parents"):
                lines.append(f"- **Parents (is_a)**: {', '.join(t['parents'])}")
            lines.append("")
    else:
        lines += ["", "_No ontology terms matched._", ""]
    lines += ["---", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Live OLS search (optional)
# ---------------------------------------------------------------------------

def fetch_live(query):  # pragma: no cover - network path
    """Best-effort EBI OLS search across plant ontologies. Returns [] on failure."""
    import urllib.parse
    import urllib.request
    url = ("https://www.ebi.ac.uk/ols4/api/search?q=" + urllib.parse.quote(query)
           + "&ontology=po,to,peco")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        out = []
        for doc in data.get("response", {}).get("docs", []):
            out.append({
                "id": doc.get("obo_id", doc.get("short_form", "NA")),
                "name": doc.get("label", "NA"),
                "ontology": doc.get("ontology_prefix", "NA"),
                "definition": (doc.get("description") or [""])[0],
                "parents": [], "synonyms": doc.get("synonym", []),
            })
        return out
    except Exception as exc:
        print(f"[crop-ontology] live OLS query failed ({exc}); using offline set.", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(out_dir: Path, report_md, results, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md)
    (out_dir / "result.json").write_text(json.dumps({"meta": meta, "terms": results}, indent=2))
    tables = out_dir / "tables"
    tables.mkdir(exist_ok=True)
    cols = ["id", "name", "ontology", "definition"]
    csv_lines = [",".join(cols)]
    for t in results:
        row = [str(t.get(c, "")).replace(",", ";") for c in cols]
        csv_lines.append(",".join(row))
    (tables / "terms.csv").write_text("\n".join(csv_lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Crop & Plant Ontology lookup (ClawBioCrop)")
    p.add_argument("--query", help="Free-text trait/anatomy/condition query")
    p.add_argument("--term", help="Exact ontology id, e.g. TO:0000396")
    p.add_argument("--ontology", choices=list(ONTOLOGIES.keys()), help="Restrict to one ontology")
    p.add_argument("--output", default="/tmp/ontology", help="Output directory")
    p.add_argument("--live", action="store_true", help="Attempt live EBI OLS search")
    p.add_argument("--demo", action="store_true", help="Run with a demo query")
    args = p.parse_args(argv)

    query = None
    term_id = None
    if args.demo:
        query = "grain yield"
        results = search_terms(query)
    elif args.term:
        term_id = args.term
        t = get_term(term_id)
        results = [t] if t else []
    elif args.query:
        query = args.query
        results = fetch_live(query) if args.live else []
        if not results:
            results = search_terms(query, ontology=args.ontology)
    else:
        p.error("provide --query, --term, or --demo")

    report_md = generate_report(query, results, term_id=term_id)
    meta = {"query": query, "term": term_id, "n_matches": len(results),
            "generated": datetime.now().isoformat()}
    out_dir = Path(args.output)
    write_outputs(out_dir, report_md, results, meta)
    print(report_md)
    print(f"\n[crop-ontology] Wrote report to {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
