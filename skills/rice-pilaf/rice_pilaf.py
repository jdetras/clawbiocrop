#!/usr/bin/env python3
"""
rice_pilaf.py — RicePilaf Post-GWAS/QTL Browser (ClawBioCrop Skill)
===================================================================
Post-GWAS and post-QTL analysis for rice (*Oryza sativa*), inspired by RicePilaf
(https://github.com/bioinfodlsu/rice-pilaf). Given GWAS/QTL peak intervals on the
Nipponbare IRGSP-1.0/MSU7 reference, it lifts the loci to candidate genes, attaches
MSU/RAP annotation, summarises by trait-ontology category, and flags priority
candidates for follow-up.

Usage:
    python rice_pilaf.py --loci chr01:1000000-1010000,chr03:200000-260000 --output /tmp/pilaf
    python rice_pilaf.py --bed peaks.bed --output /tmp/pilaf
    python rice_pilaf.py --demo --output /tmp/pilaf_demo

OFFLINE-FIRST: --demo and the bundled annotation slice work without network.

ClawBioCrop is a research and educational tool for crop genomics, not a
breeding-decision system. Validate candidates against primary IRRI resources.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. It is not a "
    "breeding-decision system and does not replace field validation. Confirm candidate "
    "genes against primary IRRI / RAP-DB / MSU resources before acting on them."
)

# ---------------------------------------------------------------------------
# Bundled candidate-gene annotation slice (synthetic, IRGSP-1.0/MSU7-shaped).
# trait_category uses Plant/Trait Ontology-style buckets.
# ---------------------------------------------------------------------------
GENE_MODELS = [
    {"gene": "LOC_Os01g01010", "chrom": "chr01", "start": 1000000, "end": 1002000,
     "rap": "Os01g0100100", "symbol": "OsTPS1", "trait_category": "yield",
     "description": "trehalose-6-phosphate synthase, grain filling"},
    {"gene": "LOC_Os01g01040", "chrom": "chr01", "start": 1008500, "end": 1009100,
     "rap": "Os01g0100700", "symbol": "OsbZIP01", "trait_category": "abiotic-stress",
     "description": "bZIP transcription factor, drought response"},
    {"gene": "LOC_Os03g03200", "chrom": "chr03", "start": 205000, "end": 209000,
     "rap": "Os03g0123400", "symbol": "Sub1A", "trait_category": "abiotic-stress",
     "description": "ethylene-response factor, submergence tolerance"},
    {"gene": "LOC_Os03g03450", "chrom": "chr03", "start": 240000, "end": 244000,
     "rap": "Os03g0145600", "symbol": "OsWRKY45", "trait_category": "biotic-stress",
     "description": "WRKY transcription factor, blast resistance"},
    {"gene": "LOC_Os07g07890", "chrom": "chr07", "start": 5400000, "end": 5404000,
     "rap": "Os07g0456700", "symbol": "GW7", "trait_category": "yield",
     "description": "grain width and weight regulator"},
]


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

def parse_loci(spec: str):
    """Parse 'chr01:1000000-1010000,chr03:200000-260000' into intervals."""
    intervals = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        chrom, span = chunk.split(":")
        start, end = span.split("-")
        intervals.append({"chrom": chrom.strip(), "start": int(start), "end": int(end)})
    if not intervals:
        raise ValueError("No valid loci parsed. Use CHROM:START-END,CHROM:START-END")
    return intervals


def parse_bed(path: Path):
    """Parse a minimal BED file (chrom, start, end) into intervals."""
    intervals = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "track", "browser")):
            continue
        fields = line.split()
        intervals.append({"chrom": fields[0], "start": int(fields[1]), "end": int(fields[2])})
    if not intervals:
        raise ValueError(f"No intervals found in BED file {path}")
    return intervals


# ---------------------------------------------------------------------------
# Core post-GWAS logic: lift intervals to overlapping candidate genes
# ---------------------------------------------------------------------------

def candidate_genes(intervals, genes=None):
    """Return genes whose models overlap any input interval, tagged by source locus."""
    pool = genes if genes is not None else GENE_MODELS
    hits = []
    seen = set()
    for iv in intervals:
        for g in pool:
            if g["chrom"] != iv["chrom"]:
                continue
            if g["start"] <= iv["end"] and g["end"] >= iv["start"]:  # overlap
                key = g["gene"]
                if key in seen:
                    continue
                seen.add(key)
                rec = dict(g)
                rec["source_locus"] = f"{iv['chrom']}:{iv['start']}-{iv['end']}"
                hits.append(rec)
    return sorted(hits, key=lambda g: (g["chrom"], g["start"]))


def enrichment_summary(hits):
    """Count candidate genes per trait-ontology category."""
    counts = {}
    for g in hits:
        counts[g["trait_category"]] = counts.get(g["trait_category"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def prioritise(hits):
    """Rank candidates: known-symbol stress/yield genes first."""
    priority_cats = {"abiotic-stress", "biotic-stress", "yield"}

    def score(g):
        s = 0
        # Named genes (e.g. Sub1A, GW7) rank above generic OsXXX symbols.
        symbol = g.get("symbol", "")
        if symbol and not symbol.startswith("Os"):
            s += 1
        if g["trait_category"] in priority_cats:
            s += 1
        return s

    return sorted(hits, key=lambda g: (-score(g), g["gene"]))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(intervals, hits):
    enrich = enrichment_summary(hits)
    ranked = prioritise(hits)
    lines = [
        "# RicePilaf Post-GWAS / QTL Report",
        "",
        "**Reference**: Nipponbare IRGSP-1.0 / MSU7  ",
        f"**Input loci**: {len(intervals)}  ",
        f"**Candidate genes**: {len(hits)}  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Input intervals",
        "",
        "| # | Region |",
        "|---|--------|",
    ]
    for i, iv in enumerate(intervals, 1):
        lines.append(f"| {i} | {iv['chrom']}:{iv['start']:,}-{iv['end']:,} |")
    lines += [
        "",
        "## Candidate genes",
        "",
        "| Gene (MSU) | RAP | Symbol | Trait category | Description |",
        "|------------|-----|--------|----------------|-------------|",
    ]
    for g in ranked:
        lines.append(
            f"| {g['gene']} | {g['rap']} | {g['symbol']} | {g['trait_category']} | {g['description']} |"
        )
    lines += [
        "",
        "## Trait-category enrichment",
        "",
        "| Trait category | Candidate genes |",
        "|----------------|-----------------|",
    ]
    for cat, n in enrich.items():
        lines.append(f"| {cat} | {n} |")
    lines += [
        "",
        "## Priority candidates",
        "",
        _priority_text(ranked),
        "",
        "---",
        "",
        f"*{DISCLAIMER}*",
        "",
    ]
    return "\n".join(lines)


def _priority_text(ranked):
    if not ranked:
        return "No candidate genes overlapped the input loci in the bundled annotation."
    top = ranked[:3]
    bullets = [
        f"- **{g['symbol']}** ({g['gene']}) — {g['trait_category']}: {g['description']}"
        for g in top
    ]
    return "Top candidates for functional follow-up:\n\n" + "\n".join(bullets)


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(out_dir: Path, report_md, intervals, hits):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md)
    result = {
        "meta": {"reference": "IRGSP-1.0/MSU7", "n_loci": len(intervals),
                 "n_candidates": len(hits), "generated": datetime.now().isoformat()},
        "intervals": intervals,
        "candidate_genes": hits,
        "enrichment": enrichment_summary(hits),
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    tables = out_dir / "tables"
    tables.mkdir(exist_ok=True)
    cols = ["gene", "rap", "symbol", "trait_category", "chrom", "start", "end", "source_locus"]
    csv_lines = [",".join(cols)]
    for g in hits:
        csv_lines.append(",".join(str(g.get(c, "")) for c in cols))
    (tables / "candidate_genes.csv").write_text("\n".join(csv_lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="RicePilaf post-GWAS/QTL browser (ClawBioCrop)")
    p.add_argument("--loci", help="Comma-separated CHROM:START-END intervals")
    p.add_argument("--bed", help="BED file of GWAS/QTL peak intervals")
    p.add_argument("--output", default="/tmp/pilaf", help="Output directory")
    p.add_argument("--demo", action="store_true", help="Run with bundled demo loci")
    args = p.parse_args(argv)

    if args.demo:
        intervals = [
            {"chrom": "chr01", "start": 1000000, "end": 1010000},
            {"chrom": "chr03", "start": 200000, "end": 260000},
            {"chrom": "chr07", "start": 5390000, "end": 5410000},
        ]
    elif args.bed:
        intervals = parse_bed(Path(args.bed))
    elif args.loci:
        intervals = parse_loci(args.loci)
    else:
        p.error("provide --loci, --bed, or --demo")

    hits = candidate_genes(intervals)
    report_md = generate_report(intervals, hits)
    out_dir = Path(args.output)
    write_outputs(out_dir, report_md, intervals, hits)
    print(report_md)
    print(f"\n[rice-pilaf] Wrote report to {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
