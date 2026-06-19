#!/usr/bin/env python3
"""
snp_seek.py — SNP-Seek Rice Variant Explorer (ClawBioCrop Skill)
================================================================
Query the IRRI SNP-Seek database (https://snp-seek.irri.org) for rice
(*Oryza sativa*) SNPs from the 3,000 Rice Genomes Project (3K-RGP), aligned to
the Nipponbare IRGSP-1.0 / MSU7 reference. Look up variants by genomic region,
inspect allele states across rice varietal groups (indica, japonica, aus, aromatic),
and resolve MSU/RAP gene loci to coordinates.

Usage:
    python snp_seek.py --region chr01:1000000-1010000 --output /tmp/snpseek
    python snp_seek.py --locus LOC_Os01g01010 --output /tmp/snpseek
    python snp_seek.py --demo --output /tmp/snpseek_demo

This skill is OFFLINE-FIRST: --demo and the bundled reference work without network.
Live queries against the SNP-Seek REST API are attempted only when --live is set.

ClawBioCrop is a research and educational tool for crop genomics. It is not a
breeding-decision system; validate findings against primary IRRI data.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEMO_DATA = SKILL_DIR / "examples" / "demo_snps.json"

# SNP-Seek live API base (used only with --live).
SNPSEEK_API = "https://snp-seek.irri.org/ws"

# Rice varietal groups tracked by the 3K-RGP genotype matrix.
VARIETAL_GROUPS = ["indica", "japonica", "aus", "aromatic", "admixed"]

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. It is not "
    "a breeding-decision system and does not replace field validation. Confirm any "
    "variant before acting on it against primary IRRI SNP-Seek data."
)

# ---------------------------------------------------------------------------
# Bundled demo dataset — a synthetic but realistically-shaped slice of the
# 3K-RGP genotype matrix on chr01 near LOC_Os01g01010 (no real genotypes).
# ---------------------------------------------------------------------------
DEMO_SNPS = [
    {"snp_id": "sf0100000123", "chrom": "chr01", "pos": 1000123, "ref": "A", "alt": "G",
     "locus": "LOC_Os01g01010", "maf": 0.31, "effect": "missense",
     "group_alt_freq": {"indica": 0.52, "japonica": 0.04, "aus": 0.28, "aromatic": 0.11, "admixed": 0.30}},
    {"snp_id": "sf0100001890", "chrom": "chr01", "pos": 1001890, "ref": "C", "alt": "T",
     "locus": "LOC_Os01g01010", "maf": 0.18, "effect": "synonymous",
     "group_alt_freq": {"indica": 0.21, "japonica": 0.15, "aus": 0.19, "aromatic": 0.12, "admixed": 0.18}},
    {"snp_id": "sf0100003402", "chrom": "chr01", "pos": 1003402, "ref": "G", "alt": "A",
     "locus": "LOC_Os01g01019", "maf": 0.44, "effect": "intron",
     "group_alt_freq": {"indica": 0.41, "japonica": 0.49, "aus": 0.40, "aromatic": 0.46, "admixed": 0.44}},
    {"snp_id": "sf0100005118", "chrom": "chr01", "pos": 1005118, "ref": "T", "alt": "C",
     "locus": "LOC_Os01g01030", "maf": 0.07, "effect": "upstream",
     "group_alt_freq": {"indica": 0.02, "japonica": 0.14, "aus": 0.05, "aromatic": 0.03, "admixed": 0.07}},
    {"snp_id": "sf0100008771", "chrom": "chr01", "pos": 1008771, "ref": "A", "alt": "T",
     "locus": "LOC_Os01g01040", "maf": 0.49, "effect": "missense",
     "group_alt_freq": {"indica": 0.50, "japonica": 0.48, "aus": 0.51, "aromatic": 0.47, "admixed": 0.49}},
]

# Minimal MSU locus → coordinate map for offline locus resolution.
LOCUS_INDEX = {
    "LOC_Os01g01010": {"chrom": "chr01", "start": 1000000, "end": 1002000},
    "LOC_Os01g01019": {"chrom": "chr01", "start": 1003000, "end": 1003800},
    "LOC_Os01g01030": {"chrom": "chr01", "start": 1004800, "end": 1005400},
    "LOC_Os01g01040": {"chrom": "chr01", "start": 1008500, "end": 1009100},
}


# ---------------------------------------------------------------------------
# Core query logic
# ---------------------------------------------------------------------------

def parse_region(region: str):
    """Parse 'chr01:1000000-1010000' into (chrom, start, end)."""
    try:
        chrom, span = region.split(":")
        start, end = span.split("-")
        return chrom.strip(), int(start), int(end)
    except ValueError:
        raise ValueError(
            f"Invalid region '{region}'. Use CHROM:START-END, e.g. chr01:1000000-1010000"
        )


def resolve_locus(locus: str):
    """Resolve an MSU locus id to a genomic region using the offline index."""
    key = locus.strip()
    if key not in LOCUS_INDEX:
        raise ValueError(
            f"Locus '{locus}' not in offline index. Known: {', '.join(sorted(LOCUS_INDEX))}"
        )
    loc = LOCUS_INDEX[key]
    return loc["chrom"], loc["start"], loc["end"]


def query_region(chrom: str, start: int, end: int, snps=None):
    """Return all SNPs within [start, end] on chrom from the dataset."""
    pool = snps if snps is not None else DEMO_SNPS
    hits = [s for s in pool if s["chrom"] == chrom and start <= s["pos"] <= end]
    return sorted(hits, key=lambda s: s["pos"])


def summarise_groups(hits):
    """Compute per-varietal-group mean alt-allele frequency across hits."""
    if not hits:
        return {g: 0.0 for g in VARIETAL_GROUPS}
    summary = {}
    for g in VARIETAL_GROUPS:
        vals = [s["group_alt_freq"].get(g, 0.0) for s in hits]
        summary[g] = round(sum(vals) / len(vals), 4)
    return summary


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(chrom, start, end, hits, locus=None, live=False):
    """Build a Markdown report string from query hits."""
    group_summary = summarise_groups(hits)
    region_label = f"{chrom}:{start:,}-{end:,}"
    source = "SNP-Seek live REST API" if live else "bundled 3K-RGP demo slice"
    lines = [
        "# SNP-Seek Rice Variant Report",
        "",
        f"**Reference**: Nipponbare IRGSP-1.0 / MSU7  ",
        f"**Panel**: 3,000 Rice Genomes Project (3K-RGP)  ",
        f"**Region**: {region_label}  ",
    ]
    if locus:
        lines.append(f"**Locus**: {locus}  ")
    lines += [
        f"**Source**: {source}  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}  ",
        f"**SNPs found**: {len(hits)}",
        "",
        "## Variants",
        "",
        "| SNP ID | Pos | Ref/Alt | Locus | Effect | MAF |",
        "|--------|-----|---------|-------|--------|-----|",
    ]
    for s in hits:
        lines.append(
            f"| {s['snp_id']} | {s['pos']:,} | {s['ref']}/{s['alt']} | "
            f"{s['locus']} | {s['effect']} | {s['maf']:.2f} |"
        )
    lines += [
        "",
        "## Mean alt-allele frequency by varietal group",
        "",
        "| Varietal group | Mean alt freq |",
        "|----------------|---------------|",
    ]
    for g in VARIETAL_GROUPS:
        lines.append(f"| {g} | {group_summary[g]:.3f} |")
    lines += [
        "",
        "## Interpretation",
        "",
        _interpret(hits, group_summary),
        "",
        "---",
        "",
        f"*{DISCLAIMER}*",
        "",
    ]
    return "\n".join(lines)


def _interpret(hits, group_summary):
    if not hits:
        return "No SNPs were found in this region within the demo panel."
    diffs = max(group_summary.values()) - min(group_summary.values())
    note = (
        "Marked indica/japonica divergence in alt-allele frequency suggests this "
        "region may carry subpopulation-differentiating variation worth following up "
        "in a GWAS or selection scan."
        if diffs >= 0.25 else
        "Allele frequencies are broadly similar across varietal groups, suggesting "
        "no strong subpopulation differentiation in this window."
    )
    missense = [s for s in hits if s["effect"] == "missense"]
    extra = (
        f" {len(missense)} missense variant(s) present — prioritise for functional review."
        if missense else ""
    )
    return note + extra


# ---------------------------------------------------------------------------
# Live API (optional, best-effort)
# ---------------------------------------------------------------------------

def fetch_live(chrom, start, end):  # pragma: no cover - network path
    """Best-effort live query against SNP-Seek. Returns [] on any failure."""
    import urllib.request
    url = f"{SNPSEEK_API}/genotype/region/{chrom}/{start}/{end}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        # Normalise to our internal shape (best-effort; schema may vary).
        out = []
        for rec in data if isinstance(data, list) else data.get("snps", []):
            out.append({
                "snp_id": rec.get("snpId", rec.get("id", "NA")),
                "chrom": chrom,
                "pos": int(rec.get("pos", rec.get("position", 0))),
                "ref": rec.get("ref", "N"),
                "alt": rec.get("alt", "N"),
                "locus": rec.get("locus", "NA"),
                "effect": rec.get("effect", "unknown"),
                "maf": float(rec.get("maf", 0.0)),
                "group_alt_freq": {g: 0.0 for g in VARIETAL_GROUPS},
            })
        return out
    except Exception as exc:
        print(f"[snp-seek] live query failed ({exc}); falling back offline.", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(out_dir: Path, report_md: str, hits, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md)
    result = {"meta": meta, "snps": hits, "group_summary": summarise_groups(hits)}
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    tables = out_dir / "tables"
    tables.mkdir(exist_ok=True)
    cols = ["snp_id", "chrom", "pos", "ref", "alt", "locus", "effect", "maf"]
    csv_lines = [",".join(cols)]
    for s in hits:
        csv_lines.append(",".join(str(s[c]) for c in cols))
    (tables / "snps.csv").write_text("\n".join(csv_lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="SNP-Seek rice variant explorer (ClawBioCrop)")
    p.add_argument("--region", help="Genomic region CHROM:START-END, e.g. chr01:1000000-1010000")
    p.add_argument("--locus", help="MSU locus id, e.g. LOC_Os01g01010")
    p.add_argument("--output", default="/tmp/snpseek", help="Output directory")
    p.add_argument("--live", action="store_true", help="Attempt live SNP-Seek REST query")
    p.add_argument("--demo", action="store_true", help="Run with bundled demo region")
    args = p.parse_args(argv)

    locus = None
    if args.demo:
        chrom, start, end = "chr01", 1000000, 1010000
    elif args.locus:
        locus = args.locus
        chrom, start, end = resolve_locus(args.locus)
    elif args.region:
        chrom, start, end = parse_region(args.region)
    else:
        p.error("provide --region, --locus, or --demo")

    hits = []
    if args.live and not args.demo:
        hits = fetch_live(chrom, start, end)
    if not hits:
        hits = query_region(chrom, start, end)

    report_md = generate_report(chrom, start, end, hits, locus=locus, live=bool(args.live and hits))
    meta = {
        "reference": "IRGSP-1.0/MSU7", "panel": "3K-RGP",
        "region": f"{chrom}:{start}-{end}", "locus": locus,
        "n_snps": len(hits), "generated": datetime.now().isoformat(),
    }
    out_dir = Path(args.output)
    write_outputs(out_dir, report_md, hits, meta)
    print(report_md)
    print(f"\n[snp-seek] Wrote report to {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
