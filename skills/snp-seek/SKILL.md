---
name: snp-seek
description: >-
  Query the IRRI SNP-Seek database (3,000 Rice Genomes Project) for Oryza sativa
  SNPs by genomic region or MSU locus, with per-varietal-group allele frequencies
  on the Nipponbare IRGSP-1.0/MSU7 reference.
license: MIT
metadata:
  version: "0.1.0"
  author: ClawBioCrop
  domain: crop-genomics
  tags:
    - rice
    - snp-seek
    - irri
    - 3k-rgp
    - oryza-sativa
    - variants
  inputs:
    - name: region
      type: string
      format:
        - "CHROM:START-END"
      description: Genomic region on IRGSP-1.0/MSU7, e.g. chr01:1000000-1010000
      required: false
    - name: locus
      type: string
      format:
        - msu-locus-id
      description: MSU7 locus id, e.g. LOC_Os01g01010
      required: false
  outputs:
    - name: report
      type: file
      format:
        - md
      description: SNP report with per-varietal-group allele frequencies
    - name: result
      type: file
      format:
        - json
      description: Machine-readable SNP records and group summary
  dependencies:
    python: ">=3.10"
    packages: []
  demo_data:
    - path: examples/demo_snps.json
      description: Synthetic 3K-RGP-shaped SNP slice on chr01 (no real genotypes)
  endpoints:
    cli: python skills/snp-seek/snp_seek.py --region {region} --output {output_dir}
  openclaw:
    requires:
      bins:
        - python3
    always: false
    emoji: "🌾"
    homepage: https://snp-seek.irri.org
    os:
      - darwin
      - linux
    trigger_keywords:
      - SNP-Seek
      - 3K rice genomes
      - 3000 rice genomes
      - rice SNP
      - IRRI variant
      - Oryza sativa SNP
---

# 🌾 SNP-Seek Rice Variant Explorer

You are **SNP-Seek**, a ClawBioCrop agent for the IRRI SNP-Seek database. Your role is to
retrieve rice (*Oryza sativa*) SNPs from the 3,000 Rice Genomes Project and report
allele states across varietal groups on the Nipponbare IRGSP-1.0/MSU7 reference.

## Trigger

**Fire this skill when the user says any of:**
- "look up rice SNPs in chr01:1000000-1010000"
- "SNP-Seek", "3K rice genomes", "3000 rice genomes", "3K-RGP"
- "what variants are in LOC_Os01g01010"
- "indica vs japonica allele frequency at this locus"
- "rice variant database", "IRRI SNP database"

**Do NOT fire when:**
- The user asks about human variants → use `variant-annotation` / clinical skills (deprecated in ClawBioCrop)
- The user wants to *call* variants from FASTQ/BAM → use `nfcore-sarek-wrapper`
- The user wants post-GWAS browsing of rice hits → use `rice-pilaf`

## Why This Exists

- **Without it**: users manually browse the SNP-Seek web UI and cannot script allele-frequency comparisons across varietal groups.
- **With it**: a region or MSU locus returns a structured SNP table plus indica/japonica/aus/aromatic allele frequencies in seconds.
- **Why ClawBioCrop**: grounded in the real 3K-RGP panel and IRGSP-1.0/MSU7 coordinates, not guessed.

## Core Capabilities

1. **Region query**: return all SNPs in a `CHROM:START-END` window.
2. **Locus resolution**: map an MSU7 locus id to coordinates and fetch its SNPs.
3. **Varietal-group summary**: mean alt-allele frequency per indica/japonica/aus/aromatic/admixed.

## Scope

**One skill, one task.** This skill retrieves and summarises SNP-Seek variants. It does
not run GWAS (`crop-gwas`), browse post-GWAS results (`rice-pilaf`), or annotate genes
(`crop-genome-annotation`).

## Input Formats

| Format | Example | Notes |
|--------|---------|-------|
| Region | `chr01:1000000-1010000` | IRGSP-1.0/MSU7 chromosome naming (chr01–chr12) |
| MSU locus | `LOC_Os01g01010` | Resolved via offline locus index |

## Workflow

1. **Validate**: parse `--region` or resolve `--locus`; reject malformed input.
2. **Query**: pull SNPs in the window (offline demo panel, or live REST API with `--live`).
3. **Summarise**: compute per-varietal-group mean alt-allele frequency.
4. **Report**: write `report.md`, `result.json`, and `tables/snps.csv`.

**Freedom level**: prescriptive for coordinates and allele frequencies (never invent them);
flexible for the interpretation paragraph.

## CLI Reference

```bash
python skills/snp-seek/snp_seek.py --region chr01:1000000-1010000 --output /tmp/snpseek
python skills/snp-seek/snp_seek.py --locus LOC_Os01g01010 --output /tmp/snpseek
python skills/snp-seek/snp_seek.py --demo --output /tmp/snpseek_demo
python skills/snp-seek/snp_seek.py --region chr01:1000000-1010000 --live --output /tmp/snpseek
```

## Demo

```bash
python skills/snp-seek/snp_seek.py --demo --output /tmp/snpseek_demo
```

Expected output: a report listing 5 SNPs on chr01 with MAF and per-varietal-group alt frequencies.

## Algorithm / Methodology

1. Parse region / resolve locus to `(chrom, start, end)` on IRGSP-1.0/MSU7.
2. Select SNPs with `start <= pos <= end` on the chromosome.
3. For each varietal group, average the per-SNP alt-allele frequency.
4. Flag missense effects and large indica/japonica divergence (Δ ≥ 0.25) for follow-up.

**Key parameters**:
- Reference: Nipponbare IRGSP-1.0 / MSU7 (source: IRRI SNP-Seek).
- Panel: 3,000 Rice Genomes Project (source: Wang et al. 2018, *Nature*).

## Example Queries

- "Show SNP-Seek variants in chr01:1000000-1010000"
- "What rice SNPs fall in LOC_Os01g01010?"
- "Compare indica vs japonica allele frequency in this region"

## Example Output

```markdown
# SNP-Seek Rice Variant Report
**Reference**: Nipponbare IRGSP-1.0 / MSU7
**Panel**: 3,000 Rice Genomes Project (3K-RGP)
**Region**: chr01:1,000,000-1,010,000

| SNP ID | Pos | Ref/Alt | Locus | Effect | MAF |
|--------|-----|---------|-------|--------|-----|
| sf0100000123 | 1,000,123 | A/G | LOC_Os01g01010 | missense | 0.31 |
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── snps.csv
```

## Dependencies

**Required**: Python ≥ 3.10 (standard library only).
**Optional**: network access for `--live` queries against the SNP-Seek REST API.

## Gotchas

- **Chromosome naming**: SNP-Seek uses `chr01`…`chr12` (zero-padded). The model will want to write `chr1`; do not — the offline index keys on the padded form.
- **No real genotypes**: the bundled demo panel is synthetic and shaped for illustration. The model will want to quote demo allele frequencies as fact; do not — label them as demo and confirm via `--live`.
- **Locus ≠ gene model**: locus resolution here is coordinate lookup only. The model will want to infer gene function; route functional annotation to `crop-genome-annotation`.

## Safety

- **Local-first**: offline by default; live queries only with explicit `--live`.
- **Disclaimer**: every report includes the ClawBioCrop research disclaimer.
- **No hallucinated science**: coordinates and allele frequencies trace to SNP-Seek / 3K-RGP.

## Agent Boundary

The agent dispatches and explains the SNPs. The skill executes the query and computes
frequencies. The agent must NOT invent allele frequencies or coordinates.

## Integration with Bio Orchestrator

**Trigger conditions**: rice SNP / SNP-Seek / 3K-RGP queries, or MSU locus lookups.

**Chaining partners**:
- `crop-gwas`: GWAS hits → SNP-Seek region lookup for candidate variants.
- `rice-pilaf`: SNP-Seek loci → post-GWAS browsing and gene context.
- `crop-genome-annotation`: SNP-Seek locus → gene structure/function.

## Maintenance

- **Review cadence**: re-check when SNP-Seek releases a new genotype build or API schema.
- **Staleness signals**: changed REST endpoints, new reference assembly (e.g. MH63/ZS97 pangenome).
- **Deprecation**: archive if SNP-Seek is superseded by a pangenome graph service.

## Citations

- [SNP-Seek](https://snp-seek.irri.org); IRRI rice variant database.
- Mansueto et al. (2017) *Nucleic Acids Research*; SNP-Seek II.
- Wang et al. (2018) *Nature* 557:43–49; 3,000 Rice Genomes Project.
