#!/usr/bin/env python3
"""
crop_gwas.py — Crop GWAS Association Scan (ClawBioCrop Skill)
============================================================
Run a lightweight genome-wide association scan for crop / plant breeding
populations. Given a genotype dosage matrix (samples × SNPs, coded 0/1/2) and a
quantitative phenotype, fit a per-SNP linear model (y ~ allele_dosage), compute
effect size, p-value, and genomic inflation (lambda_GC), then report Bonferroni-
significant hits ready for hand-off to RicePilaf / SNP-Seek.

Usage:
    python crop_gwas.py --genotypes geno.csv --phenotype pheno.csv \
        --trait grain_yield --output /tmp/gwas
    python crop_gwas.py --demo --output /tmp/gwas_demo

Genotype CSV: first column 'sample', remaining columns are SNP ids; header SNP id
encodes position as 'chrom:pos' (e.g. chr01:1000123). Values are 0/1/2 dosages.
Phenotype CSV: columns 'sample' and one or more trait columns.

OFFLINE-FIRST: --demo synthesises a population with planted true-positive SNPs.
Pure standard library — no numpy/scipy required.

ClawBioCrop is a research and educational tool for crop genomics, not a
breeding-decision system.
"""

import argparse
import csv
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. GWAS hits are "
    "statistical associations, not validated causal genes, and must be confirmed by "
    "replication and field validation before any breeding decision."
)


# ---------------------------------------------------------------------------
# Statistics (pure Python)
# ---------------------------------------------------------------------------

def _norm_sf(z):
    """Two-sided survival approximation via the error function (math.erf)."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def linreg_pvalue(x, y):
    """Simple linear regression y ~ x. Return (beta, r, p_value, n)."""
    n = len(x)
    if n < 3:
        return 0.0, 0.0, 1.0, n
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    if sxx == 0 or syy == 0:
        return 0.0, 0.0, 1.0, n
    beta = sxy / sxx
    r = sxy / math.sqrt(sxx * syy)
    r = max(min(r, 0.999999), -0.999999)
    # t-statistic; for moderate/large n approximate with the normal tail.
    t = r * math.sqrt((n - 2) / (1 - r * r))
    p = _norm_sf(t)
    return beta, r, max(p, 1e-300), n


def lambda_gc(pvalues):
    """Genomic inflation factor from median chi-square (1 df)."""
    if not pvalues:
        return float("nan")
    chisq = sorted(_chi1_from_p(p) for p in pvalues)
    n = len(chisq)
    med = chisq[n // 2] if n % 2 else (chisq[n // 2 - 1] + chisq[n // 2]) / 2
    return round(med / 0.4549, 4)  # 0.4549 = median of chi-square_1


def _chi1_from_p(p):
    """Inverse-survival of chi-square(1) ≈ (inverse normal)^2."""
    z = _inv_norm_sf(p / 2.0)
    return z * z


def _inv_norm_sf(p):
    """Approximate inverse survival function of the standard normal (Acklam)."""
    p = min(max(p, 1e-300), 1 - 1e-16)
    q = 1 - p  # want z such that SF(z)=p -> CDF = 1-p
    # Use rational approximation for the quantile of CDF=q.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if q < plow:
        t = math.sqrt(-2 * math.log(q))
        return (((((c[0] * t + c[1]) * t + c[2]) * t + c[3]) * t + c[4]) * t + c[5]) / \
               ((((d[0] * t + d[1]) * t + d[2]) * t + d[3]) * t + 1)
    if q > phigh:
        t = math.sqrt(-2 * math.log(1 - q))
        return -(((((c[0] * t + c[1]) * t + c[2]) * t + c[3]) * t + c[4]) * t + c[5]) / \
                 ((((d[0] * t + d[1]) * t + d[2]) * t + d[3]) * t + 1)
    t = q - 0.5
    r = t * t
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * t / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def parse_snp_id(snp_id):
    """'chr01:1000123' -> ('chr01', 1000123); fall back gracefully."""
    if ":" in snp_id:
        chrom, pos = snp_id.split(":", 1)
        try:
            return chrom, int(pos)
        except ValueError:
            return chrom, 0
    return "NA", 0


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

def run_gwas(geno_rows, pheno_rows, trait):
    """Return (results, meta). results: list of per-SNP dicts sorted by p."""
    pheno = {r["sample"]: r for r in pheno_rows}
    samples = [r["sample"] for r in geno_rows if r["sample"] in pheno]
    if not samples:
        raise ValueError("No overlapping samples between genotype and phenotype files.")
    y = []
    for s in samples:
        try:
            y.append(float(pheno[s][trait]))
        except (KeyError, ValueError):
            raise ValueError(f"Trait '{trait}' missing/non-numeric for sample {s}")

    snp_ids = [k for k in geno_rows[0].keys() if k != "sample"]
    geno_by_sample = {r["sample"]: r for r in geno_rows}
    results = []
    for snp in snp_ids:
        x = []
        for s in samples:
            try:
                x.append(float(geno_by_sample[s][snp]))
            except (KeyError, ValueError):
                x.append(0.0)
        beta, r, p, n = linreg_pvalue(x, y)
        chrom, pos = parse_snp_id(snp)
        results.append({"snp": snp, "chrom": chrom, "pos": pos,
                        "beta": round(beta, 4), "r": round(r, 4),
                        "p": p, "n": n})
    results.sort(key=lambda d: d["p"])
    m = len(results)
    bonf = 0.05 / m if m else 1.0
    for d in results:
        d["significant"] = d["p"] < bonf
        d["neglog10p"] = round(-math.log10(d["p"]), 3)
    meta = {"trait": trait, "n_samples": len(samples), "n_snps": m,
            "bonferroni_threshold": bonf,
            "lambda_gc": lambda_gc([d["p"] for d in results]),
            "n_significant": sum(d["significant"] for d in results),
            "generated": datetime.now().isoformat()}
    return results, meta


# ---------------------------------------------------------------------------
# Demo data synthesis
# ---------------------------------------------------------------------------

def synth_demo(n_samples=300, n_snps=200, n_causal=3, seed=42):
    """Synthesise a genotype/phenotype population with planted causal SNPs."""
    rng = random.Random(seed)
    snp_ids = []
    chroms = ["chr01", "chr03", "chr07"]
    for i in range(n_snps):
        chrom = chroms[i % len(chroms)]
        pos = 100000 + i * 5000
        snp_ids.append(f"{chrom}:{pos}")
    causal_idx = sorted(rng.sample(range(n_snps), n_causal))
    causal_effects = {i: rng.choice([2.0, -2.0, 2.5]) for i in causal_idx}

    geno_rows, pheno_rows = [], []
    for s in range(n_samples):
        sample = f"ACC{s:04d}"
        dosages = []
        for i in range(n_snps):
            maf = 0.1 + 0.4 * ((i * 7) % 10) / 10.0
            d = sum(1 for _ in range(2) if rng.random() < maf)
            dosages.append(d)
        pheno_val = rng.gauss(50, 5)
        for i, eff in causal_effects.items():
            pheno_val += eff * dosages[i]
        grow = {"sample": sample}
        grow.update({snp_ids[i]: dosages[i] for i in range(n_snps)})
        geno_rows.append(grow)
        pheno_rows.append({"sample": sample, "grain_yield": round(pheno_val, 3)})
    causal_snps = [snp_ids[i] for i in causal_idx]
    return geno_rows, pheno_rows, "grain_yield", causal_snps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(results, meta, causal=None):
    top = results[:15]
    lines = [
        "# Crop GWAS Association Report",
        "",
        f"**Trait**: {meta['trait']}  ",
        f"**Samples**: {meta['n_samples']}  ",
        f"**SNPs tested**: {meta['n_snps']}  ",
        f"**Genomic inflation (lambda_GC)**: {meta['lambda_gc']}  ",
        f"**Bonferroni threshold (0.05/m)**: {meta['bonferroni_threshold']:.2e}  ",
        f"**Significant SNPs**: {meta['n_significant']}  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Top associations",
        "",
        "| SNP | Chrom | Pos | Beta | -log10(p) | Significant |",
        "|-----|-------|-----|------|-----------|-------------|",
    ]
    for d in top:
        flag = "**yes**" if d["significant"] else "no"
        lines.append(
            f"| {d['snp']} | {d['chrom']} | {d['pos']:,} | {d['beta']:+.3f} | "
            f"{d['neglog10p']:.2f} | {flag} |"
        )
    lines += ["", "## Interpretation", "", _interpret(meta)]
    if causal:
        found = [d["snp"] for d in results if d["significant"]]
        recovered = [c for c in causal if c in found]
        lines += [
            "",
            "## Demo ground truth",
            "",
            f"Planted causal SNPs: {', '.join(causal)}  ",
            f"Recovered as significant: {', '.join(recovered) if recovered else 'none'}",
        ]
    lines += ["", "---", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(lines)


def _interpret(meta):
    lam = meta["lambda_gc"]
    inflation = (
        "lambda_GC is close to 1.0, indicating no major population-structure inflation."
        if 0.9 <= lam <= 1.15 else
        f"lambda_GC = {lam}: consider correcting for population structure (kinship/PCA) "
        "before trusting these p-values."
    )
    hits = meta["n_significant"]
    hit_text = (
        f"{hits} SNP(s) pass the Bonferroni threshold — forward these intervals to "
        "RicePilaf for candidate-gene lift and SNP-Seek for variant detail."
        if hits else
        "No SNP passed the Bonferroni threshold; inspect the top suggestive hits and "
        "consider a larger panel."
    )
    return f"{inflation} {hit_text}"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(out_dir, report_md, results, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md)
    (out_dir / "result.json").write_text(json.dumps({"meta": meta, "results": results[:100]}, indent=2))
    tables = out_dir / "tables"
    tables.mkdir(exist_ok=True)
    cols = ["snp", "chrom", "pos", "beta", "r", "p", "neglog10p", "significant"]
    with open(tables / "associations.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for d in results:
            w.writerow([d[c] for c in cols])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Crop GWAS association scan (ClawBioCrop)")
    p.add_argument("--genotypes", help="Genotype dosage CSV (sample + chrom:pos columns)")
    p.add_argument("--phenotype", help="Phenotype CSV (sample + trait columns)")
    p.add_argument("--trait", help="Trait column name in phenotype CSV")
    p.add_argument("--output", default="/tmp/gwas", help="Output directory")
    p.add_argument("--demo", action="store_true", help="Run with synthesised demo population")
    args = p.parse_args(argv)

    causal = None
    if args.demo:
        geno_rows, pheno_rows, trait, causal = synth_demo()
    else:
        if not (args.genotypes and args.phenotype and args.trait):
            p.error("provide --genotypes, --phenotype, and --trait (or --demo)")
        geno_rows = load_csv(args.genotypes)
        pheno_rows = load_csv(args.phenotype)
        trait = args.trait

    results, meta = run_gwas(geno_rows, pheno_rows, trait)
    report_md = generate_report(results, meta, causal=causal)
    out_dir = Path(args.output)
    write_outputs(out_dir, report_md, results, meta)
    print(report_md)
    print(f"\n[crop-gwas] Wrote report to {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
