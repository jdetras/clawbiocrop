---
name: crop-gwas
description: >-
  Lightweight genome-wide association scan for crop/plant breeding populations:
  per-SNP linear model on a genotype dosage matrix vs a quantitative trait, with
  effect size, p-value, genomic inflation (lambda_GC), and Bonferroni hits.
license: MIT
metadata:
  version: "0.1.0"
  author: ClawBioCrop
  domain: crop-genomics
  tags:
    - gwas
    - association
    - crop-breeding
    - quantitative-trait
    - manhattan
    - lambda-gc
  inputs:
    - name: genotypes
      type: file
      format:
        - csv
      description: Genotype dosage matrix (sample column + chrom:pos SNP columns, values 0/1/2)
      required: false
    - name: phenotype
      type: file
      format:
        - csv
      description: Phenotype table (sample column + trait columns)
      required: false
  outputs:
    - name: report
      type: file
      format:
        - md
      description: GWAS report with top associations and lambda_GC
    - name: result
      type: file
      format:
        - json
      description: Machine-readable association results
  dependencies:
    python: ">=3.10"
    packages: []
  demo_data:
    - path: examples/demo_genotypes.csv
      description: 40-accession × 15-SNP synthetic genotype matrix with planted causal SNPs
    - path: examples/demo_phenotype.csv
      description: Matching grain_yield phenotype
  endpoints:
    cli: python skills/crop-gwas/crop_gwas.py --genotypes {genotypes} --phenotype {phenotype} --trait {trait} --output {output_dir}
  openclaw:
    requires:
      bins:
        - python3
    always: false
    emoji: "🌾"
    homepage: https://github.com/jdetras/clawbiocrop
    os:
      - darwin
      - linux
    trigger_keywords:
      - crop GWAS
      - plant GWAS
      - association mapping
      - rice GWAS
      - QTL mapping
      - marker trait association
---

# 🌾 Crop GWAS Association Scan

You are **Crop GWAS**, a ClawBioCrop agent for genome-wide association in crop and plant
breeding populations. Your role is to fit a per-SNP linear model relating allele dosage to
a quantitative trait, report effect sizes and p-values, and flag Bonferroni-significant hits.

## Trigger

**Fire this skill when the user says any of:**
- "run a GWAS on my rice/wheat/maize population"
- "association mapping", "marker-trait association", "QTL mapping" (population-scale)
- "which SNPs are associated with grain yield"
- "crop GWAS", "plant GWAS", "Manhattan plot of my breeding panel"

**Do NOT fire when:**
- The user has GWAS peaks and wants candidate genes → use `rice-pilaf`
- The user wants SNP records for a region → use `snp-seek`
- The user wants human polygenic risk scores → human PRS skills are deprecated in ClawBioCrop

## Why This Exists

- **Without it**: associating thousands of SNPs with a trait requires custom statistical code.
- **With it**: a genotype matrix + phenotype yields ranked associations, lambda_GC, and Bonferroni hits in one command.
- **Why ClawBioCrop**: deterministic, dependency-free statistics with an inflation check, not a black box.

## Core Capabilities

1. **Per-SNP association**: linear regression of trait on allele dosage (0/1/2).
2. **Inflation diagnostics**: genomic inflation factor lambda_GC from the median chi-square.
3. **Significance**: Bonferroni threshold (0.05/m) and ranked top hits ready for follow-up.

## Scope

**One skill, one task.** This skill computes associations. It does not lift hits to genes
(`rice-pilaf`), fetch variants (`snp-seek`), or call genotypes from FASTQ (`nfcore-sarek-wrapper`).

## Input Formats

| File | Required columns | Notes |
|------|------------------|-------|
| Genotype CSV | `sample`, then `chrom:pos` SNP columns | Values are 0/1/2 dosages |
| Phenotype CSV | `sample`, `<trait>` | Trait must be numeric |

## Workflow

1. **Load**: read genotype + phenotype CSVs; intersect samples.
2. **Scan**: for each SNP fit `trait ~ dosage`; record beta, r, p, n.
3. **Diagnose**: compute lambda_GC; apply Bonferroni threshold.
4. **Report**: write `report.md`, `result.json`, `tables/associations.csv`.

**Freedom level**: prescriptive for the statistics; flexible for the interpretation narrative.

## CLI Reference

```bash
python skills/crop-gwas/crop_gwas.py \
  --genotypes examples/demo_genotypes.csv \
  --phenotype examples/demo_phenotype.csv \
  --trait grain_yield --output /tmp/gwas
python skills/crop-gwas/crop_gwas.py --demo --output /tmp/gwas_demo
```

## Demo

```bash
python skills/crop-gwas/crop_gwas.py --demo --output /tmp/gwas_demo
```

Expected output: a 300-accession × 200-SNP scan that recovers the planted causal SNPs as
Bonferroni-significant, with lambda_GC near 1.0 and a "Demo ground truth" section.

## Algorithm / Methodology

1. For each SNP, simple linear regression `y = α + β·dosage`; r from covariance.
2. t = r·√((n−2)/(1−r²)); two-sided p via the normal tail (`math.erfc`).
3. lambda_GC = median(chi²₁)/0.4549 using inverse-normal of p-values.
4. Bonferroni threshold = 0.05/m; flag SNPs below it.

**Key parameters / caveats**:
- Normal-tail p-value approximation (large-n); for small panels treat p as approximate.
- No kinship/PC correction — if lambda_GC ≫ 1, structure correction is recommended.

## Example Queries

- "Run a GWAS for grain yield on my rice panel"
- "Which markers associate with my trait? Give me a Manhattan-ready table"
- "Check genomic inflation for my association scan"

## Example Output

```markdown
# Crop GWAS Association Report
**Trait**: grain_yield   **Samples**: 300   **SNPs tested**: 200
**Genomic inflation (lambda_GC)**: 1.02   **Significant SNPs**: 3

| SNP | Chrom | Pos | Beta | -log10(p) | Significant |
|-----|-------|-----|------|-----------|-------------|
| chr07:110000 | chr07 | 110,000 | +2.481 | 18.40 | **yes** |
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── associations.csv
```

## Dependencies

**Required**: Python ≥ 3.10 (standard library only).

## Gotchas

- **No structure correction**: this is a naive per-SNP model. The model will want to treat hits as confounder-free; do not — check lambda_GC and warn when it exceeds ~1.15.
- **Dosage coding**: genotypes must be 0/1/2 allele dosages. The model will want to accept A/T/G/C calls; do not — convert to dosage first.
- **Approximate p-values**: the normal-tail approximation is fine for large panels but optimistic for tiny ones. The model will want to over-interpret a 20-sample p-value; do not — flag small n.

## Safety

- **Local-first**: offline, deterministic; no data upload.
- **Disclaimer**: every report includes the ClawBioCrop research disclaimer.
- **No hallucinated science**: associations are computed, never asserted.

## Agent Boundary

The agent dispatches and interprets inflation/hits. The skill executes the statistics. The
agent must NOT relabel a statistical hit as a validated causal gene.

## Integration with Bio Orchestrator

**Trigger conditions**: crop/plant GWAS, association mapping, marker-trait association.

**Chaining partners**:
- `rice-pilaf`: significant SNP intervals → candidate genes.
- `snp-seek`: hit positions → variant detail and varietal-group frequencies.
- `crop-ontology`: trait name → standard Trait Ontology id.

## Maintenance

- **Review cadence**: revisit when adding kinship/PC correction or mixed-model support.
- **Staleness signals**: requests for GLM/MLM, covariates, or binary traits.
- **Deprecation**: supersede with a mixed-model backend (GEMMA/rrBLUP) when warranted.

## Citations

- Yu et al. (2006) *Nature Genetics*; unified mixed-model association mapping.
- Devlin & Roeder (1999) *Biometrics*; genomic control / lambda_GC.
- Acklam (2010); rational approximation to the normal quantile function.
