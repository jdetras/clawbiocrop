---
name: rice-pilaf
description: >-
  Post-GWAS/QTL analysis for rice (Oryza sativa) inspired by RicePilaf: lift GWAS
  peak intervals to candidate genes on IRGSP-1.0/MSU7, attach MSU/RAP annotation,
  summarise by trait-ontology category, and prioritise candidates.
license: MIT
metadata:
  version: "0.1.0"
  author: ClawBioCrop
  domain: crop-genomics
  tags:
    - rice
    - rice-pilaf
    - post-gwas
    - qtl
    - candidate-genes
    - oryza-sativa
  inputs:
    - name: loci
      type: string
      format:
        - "CHROM:START-END[,...]"
      description: GWAS/QTL peak intervals on IRGSP-1.0/MSU7
      required: false
    - name: bed
      type: file
      format:
        - bed
      description: BED file of GWAS/QTL peak intervals
      required: false
  outputs:
    - name: report
      type: file
      format:
        - md
      description: Post-GWAS candidate-gene report
    - name: result
      type: file
      format:
        - json
      description: Candidate genes, intervals, and trait-category enrichment
  dependencies:
    python: ">=3.10"
    packages: []
  demo_data:
    - path: examples/demo_peaks.bed
      description: Three synthetic GWAS/QTL peak intervals on IRGSP-1.0/MSU7
  endpoints:
    cli: python skills/rice-pilaf/rice_pilaf.py --bed {bed} --output {output_dir}
  openclaw:
    requires:
      bins:
        - python3
    always: false
    emoji: "🌾"
    homepage: https://github.com/bioinfodlsu/rice-pilaf
    os:
      - darwin
      - linux
    trigger_keywords:
      - RicePilaf
      - rice pilaf
      - post-GWAS rice
      - rice QTL candidate genes
      - GWAS peak to gene rice
      - rice post-GWAS dashboard
---

# 🌾 RicePilaf Post-GWAS / QTL Browser

You are **RicePilaf**, a ClawBioCrop agent for post-GWAS and post-QTL analysis in rice.
Your role is to lift GWAS/QTL peak intervals to candidate genes on IRGSP-1.0/MSU7,
attach MSU/RAP annotation, and prioritise candidates by trait-ontology category.

## Trigger

**Fire this skill when the user says any of:**
- "RicePilaf", "rice pilaf", "post-GWAS rice", "rice post-GWAS dashboard"
- "what genes are under my rice GWAS peak"
- "candidate genes for this QTL interval"
- "lift these rice GWAS loci to genes"
- "annotate my rice GWAS hits with candidate genes"

**Do NOT fire when:**
- The user wants to *run* the GWAS association test → use `crop-gwas`
- The user wants raw SNP records for a region → use `snp-seek`
- The user wants full de novo gene structure annotation → use `crop-genome-annotation`

## Why This Exists

- **Without it**: GWAS output is a list of significant positions with no biological meaning.
- **With it**: peak intervals are lifted to named candidate genes with trait categories in seconds.
- **Why ClawBioCrop**: candidates come from real MSU/RAP gene models, not guessed annotations.

## Core Capabilities

1. **Interval-to-gene lift**: overlap GWAS/QTL intervals with MSU7 gene models.
2. **Annotation join**: attach RAP id, symbol, description, trait category.
3. **Enrichment & prioritisation**: count candidates per trait category and rank named genes first.

## Scope

**One skill, one task.** This skill turns intervals into prioritised candidate genes. It
does not compute associations (`crop-gwas`), fetch SNPs (`snp-seek`), or look up ontology
terms (`crop-ontology`).

## Input Formats

| Format | Example | Notes |
|--------|---------|-------|
| Loci string | `chr01:1000000-1010000,chr03:200000-260000` | Comma-separated intervals |
| BED file | `examples/demo_peaks.bed` | chrom / start / end (extra columns ignored) |

## Workflow

1. **Parse**: read `--loci` or `--bed` into intervals.
2. **Lift**: overlap each interval with MSU7 gene models (dedup across intervals).
3. **Annotate**: attach RAP id, symbol, trait category, description.
4. **Summarise & prioritise**: per-trait-category counts; named genes ranked first.
5. **Report**: write `report.md`, `result.json`, `tables/candidate_genes.csv`.

**Freedom level**: prescriptive for the overlap/lift (coordinates are exact); flexible for
the priority-candidate narrative.

## CLI Reference

```bash
python skills/rice-pilaf/rice_pilaf.py --loci chr01:1000000-1010000,chr03:200000-260000 --output /tmp/pilaf
python skills/rice-pilaf/rice_pilaf.py --bed examples/demo_peaks.bed --output /tmp/pilaf
python skills/rice-pilaf/rice_pilaf.py --demo --output /tmp/pilaf_demo
```

## Demo

```bash
python skills/rice-pilaf/rice_pilaf.py --demo --output /tmp/pilaf_demo
```

Expected output: a report lifting three peak intervals to candidate genes including
`Sub1A` (submergence tolerance) and `GW7` (grain width), grouped by trait category.

## Algorithm / Methodology

1. Read intervals; for each, find gene models on the same chromosome whose span overlaps.
2. Deduplicate genes seen across multiple intervals; tag each with its source locus.
3. Group candidates by trait-ontology category (yield, abiotic-stress, biotic-stress, …).
4. Prioritise: named genes (non-`Os` symbols) and priority trait categories rank first.

**Key parameters**:
- Reference: Nipponbare IRGSP-1.0 / MSU7 (source: MSU Rice Genome Annotation Project).
- Annotation: MSU ↔ RAP-DB locus mapping (source: RAP-DB).

## Example Queries

- "Lift my rice GWAS peaks chr01:1000000-1010000 and chr03:200000-260000 to genes"
- "What candidate genes sit under this submergence-tolerance QTL?"
- "Run RicePilaf on peaks.bed"

## Example Output

```markdown
# RicePilaf Post-GWAS / QTL Report
**Candidate genes**: 4

| Gene (MSU) | RAP | Symbol | Trait category | Description |
|------------|-----|--------|----------------|-------------|
| LOC_Os03g03200 | Os03g0123400 | Sub1A | abiotic-stress | submergence tolerance |
| LOC_Os07g07890 | Os07g0456700 | GW7 | yield | grain width and weight |
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── candidate_genes.csv
```

## Dependencies

**Required**: Python ≥ 3.10 (standard library only).

## Gotchas

- **Overlap, not nearest-gene**: this skill reports genes overlapping the interval. The model will want to grab the single nearest gene; do not — GWAS peaks can span several candidates.
- **Trait category ≠ causation**: a candidate in the `yield` category is a hypothesis, not a confirmed effector. The model will want to claim causation; do not — flag for functional follow-up.
- **Dedup matters**: the same gene can fall under two overlapping intervals. The model will want to double-count it in enrichment; do not — genes are deduplicated before counting.

## Safety

- **Local-first**: offline, deterministic; no data upload.
- **Disclaimer**: every report includes the ClawBioCrop research disclaimer.
- **No hallucinated science**: candidate genes trace to MSU/RAP gene models.

## Agent Boundary

The agent dispatches and narrates candidate priorities. The skill executes the interval
lift and enrichment. The agent must NOT invent genes or trait associations.

## Integration with Bio Orchestrator

**Trigger conditions**: post-GWAS rice queries, QTL-to-gene lifts, RicePilaf requests.

**Chaining partners**:
- `crop-gwas`: GWAS peaks → RicePilaf candidate genes.
- `snp-seek`: candidate-gene loci → variant detail.
- `crop-ontology`: trait category → formal Trait Ontology / Plant Ontology terms.

## Maintenance

- **Review cadence**: refresh gene models when MSU7/RAP-DB annotation updates.
- **Staleness signals**: new IRGSP build, RAP-DB re-release, RicePilaf module changes.
- **Deprecation**: archive if superseded by a hosted RicePilaf API integration.

## Citations

- [RicePilaf](https://github.com/bioinfodlsu/rice-pilaf); post-GWAS/QTL dashboard for rice.
- [RAP-DB](https://rapdb.dna.affrc.go.jp/); Rice Annotation Project Database.
- [MSU Rice Genome Annotation Project](http://rice.uga.edu/); MSU7 gene models.
