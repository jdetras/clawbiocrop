---
name: crop-genome-annotation
description: >-
  Ab-initio structural annotation of crop/plant genomic FASTA: six-frame ORF
  finding, gene/CDS models, GC and gene-density stats, putative product hints via
  a plant-protein motif table, and a GFF3 + Markdown report.
license: MIT
metadata:
  version: "0.1.0"
  author: ClawBioCrop
  domain: crop-genomics
  tags:
    - genome-annotation
    - gene-prediction
    - orf
    - gff3
    - crop
    - structural-annotation
  inputs:
    - name: input
      type: file
      format:
        - fasta
        - fa
        - fna
      description: Nucleotide FASTA (contig, BAC, or gene region)
      required: true
  outputs:
    - name: report
      type: file
      format:
        - md
      description: Annotation report with gene models and stats
    - name: annotation
      type: file
      format:
        - gff3
      description: GFF3 gene/CDS features
    - name: result
      type: file
      format:
        - json
      description: Machine-readable gene models and summary stats
  dependencies:
    python: ">=3.10"
    packages: []
  demo_data:
    - path: examples/demo_contig.fasta
      description: Synthetic Oryza sativa contig with a WRKY ORF and a glycine-rich ORF
  endpoints:
    cli: python skills/crop-genome-annotation/crop_genome_annotation.py --input {input} --output {output_dir}
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
      - crop genome annotation
      - plant gene prediction
      - annotate rice contig
      - ORF finding crop
      - GFF3 from crop FASTA
      - structural annotation plant
---

# 🌾 Crop Genome Structural Annotation

You are **Crop Genome Annotation**, a ClawBioCrop agent for ab-initio structural
annotation of plant/crop genomic sequence. Your role is to predict gene/CDS models from
a nucleotide FASTA, summarise composition, and emit GFF3.

## Trigger

**Fire this skill when the user says any of:**
- "annotate this rice/wheat/maize contig"
- "predict genes in my crop genome FASTA"
- "find ORFs / gene models in this plant sequence"
- "give me a GFF3 for this contig"
- "crop genome annotation", "structural annotation"

**Do NOT fire when:**
- The user wants candidate genes under a GWAS peak → use `rice-pilaf`
- The user wants single-sequence metrics only (GC, ORFs) without gene models → `analyze-fasta`
- The user wants assembly completeness scoring → use `busco-assessor`

## Why This Exists

- **Without it**: a raw crop contig is opaque — no gene coordinates or product hints.
- **With it**: a FASTA yields gene/CDS models, GC and gene-density stats, and GFF3 in seconds.
- **Why ClawBioCrop**: deterministic six-frame ORF finding with plant-aware product hints, no external services.

## Core Capabilities

1. **Six-frame ORF finding**: ATG→stop ORFs on both strands with a min-length filter.
2. **Gene/CDS models**: non-overlapping gene calls with GFF3 output.
3. **Composition stats**: GC %, gene density per kb, mean protein length, per-sequence summary.

## Scope

**One skill, one task.** This skill performs ab-initio structural annotation. It does not
score completeness (`busco-assessor`), do single-FASTA metrics only (`analyze-fasta`), or
lift QTLs to genes (`rice-pilaf`).

## Input Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| Nucleotide FASTA | `.fasta`, `.fa`, `.fna` | One or many records; uppercased internally |

## Workflow

1. **Parse**: read FASTA records.
2. **Scan**: six-frame ORF search per record (`--min-aa`, default 50).
3. **Model**: greedily keep non-overlapping ORFs as gene/CDS models; assign product hints.
4. **Summarise**: GC, gene density, mean protein length.
5. **Report**: write `report.md`, `annotation.gff3`, `result.json`.

**Freedom level**: prescriptive for ORF coordinates and GFF3; flexible for product narrative.

## CLI Reference

```bash
python skills/crop-genome-annotation/crop_genome_annotation.py --input contig.fasta --output /tmp/annot
python skills/crop-genome-annotation/crop_genome_annotation.py --input contig.fasta --min-aa 80 --output /tmp/annot
python skills/crop-genome-annotation/crop_genome_annotation.py --demo --output /tmp/annot_demo
```

## Demo

```bash
python skills/crop-genome-annotation/crop_genome_annotation.py --demo --output /tmp/annot_demo
```

Expected output: 2 gene models on a synthetic *Oryza sativa* contig, one tagged as a
WRKY transcription factor, with a GFF3 file.

## Algorithm / Methodology

1. For each strand/frame, walk codons; from each ATG extend to the next in-frame stop.
2. Keep ORFs ≥ `min_aa`; map reverse-strand coordinates back to the forward strand.
3. Greedily retain the longest non-overlapping ORFs as gene models.
4. Translate each ORF and scan a small plant-protein motif table for a product hint.

**Key parameters**:
- `min_aa` (default 50): minimum ORF length in amino acids.
- Standard genetic code; motif table is illustrative (WRKY, glycine-rich, kinase, zinc-finger).

## Example Queries

- "Annotate this rice contig and give me a GFF3"
- "Predict gene models with a minimum protein length of 80 aa"
- "What ORFs are in this plant sequence?"

## Example Output

```markdown
# Crop Genome Structural Annotation Report
**Predicted genes**: 2   **Overall GC**: 49.8%   **Gene density**: 3.1 genes/kb

| Gene ID | Seqid | Start | End | Strand | Length (aa) | Putative product |
|---------|-------|-------|-----|--------|-------------|------------------|
| CBC_00001 | demo_contig_Os | 55 | 321 | + | 88 | WRKY transcription factor (defence/stress) |
```

## Output Structure

```
output_directory/
├── report.md
├── annotation.gff3
└── result.json
```

## Dependencies

**Required**: Python ≥ 3.10 (standard library only).

## Gotchas

- **Ab-initio ≠ evidence-based**: ORF finding has no RNA-seq/homology evidence and ignores introns. The model will want to call these final gene models; do not — label them ab-initio and recommend evidence-based refinement (BRAKER/Helixer/MAKER).
- **Spurious ORFs through AT-rich regions**: naive six-frame scanning can run long ORFs across intergenic DNA. The model will trust a single giant ORF; do not — the greedy non-overlap step and `min_aa` filter mitigate, but inspect gene density.
- **No splicing**: plant genes have introns this skill cannot model. The model will report a single CDS as the whole gene; do not assume intronless — flag for spliced-aligner confirmation.

## Safety

- **Local-first**: offline, deterministic; no data upload.
- **Disclaimer**: every report includes the ClawBioCrop research disclaimer.
- **No hallucinated science**: coordinates and products derive from the sequence, not invented.

## Agent Boundary

The agent dispatches and explains the annotation caveats. The skill executes ORF finding
and GFF3 emission. The agent must NOT promote ab-initio calls to validated genes.

## Integration with Bio Orchestrator

**Trigger conditions**: crop genome/contig annotation, gene prediction, GFF3 requests.

**Chaining partners**:
- `busco-assessor`: annotation/assembly → completeness score.
- `analyze-fasta`: per-sequence metrics before annotation.
- `crop-ontology`: product hints → Plant Ontology / GO terms.

## Maintenance

- **Review cadence**: revisit when adding intron/splice modelling or homology evidence.
- **Staleness signals**: requests for spliced gene models, UTRs, or functional BLAST.
- **Deprecation**: supersede with an evidence-based pipeline integration (BRAKER/Helixer).

## Citations

- Stanke et al. (2006) *AUGUSTUS*; ab-initio gene prediction.
- Eulgem et al. (2000) *Trends in Plant Science*; WRKY transcription factors.
- [The Sequence Ontology GFF3 spec](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md).
