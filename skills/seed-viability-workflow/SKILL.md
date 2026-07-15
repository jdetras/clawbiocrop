---
name: seed-viability-workflow
description: >-
  End-to-end data science workflow for seed-bank viability/germination image
  collections (10x10 and 12x8 grid layouts): directory discovery, EDA over
  germination manifests, and a classification/regression model that predicts
  seed viability from accession, storage-group, and grid metadata.
license: MIT
metadata:
  version: "0.1.0"
  author: ClawBioCrop
  domain: crop-genomics
  tags:
    - seed-viability
    - germination
    - seed-bank
    - phenomics
    - image-dataset
    - object-detection
  inputs:
    - name: input_dir
      type: directory
      format:
        - directory-tree
      description: >-
        Root of a viability/ dataset tree containing 10x10/ and/or 12x8/
        subfolders (see Scope). Path is fully customizable via --input-dir;
        nothing is hardcoded.
      required: false
    - name: summary_csv
      type: file
      format:
        - csv
      description: germ_image_summary.csv (per-image manifest)
      required: false
    - name: via_csv
      type: file
      format:
        - csv
      description: via.csv (per-accession average viability result)
      required: false
  outputs:
    - name: report
      type: file
      format:
        - md
      description: Analysis + modeling report
    - name: result
      type: file
      format:
        - json
      description: Machine-readable discovery/EDA/model results
  dependencies:
    python: ">=3.10"
    packages: []
  demo_data:
    - path: examples/demo_germ_image_summary.csv
      description: Synthetic 10x10 image manifest
    - path: examples/demo_via.csv
      description: Synthetic per-accession viability results
  endpoints:
    cli: python skills/seed-viability-workflow/seed_viability_workflow.py --input-dir {input_dir} --output {output_dir}
  openclaw:
    requires:
      bins:
        - python3
    always: false
    emoji: "🌱"
    homepage: https://github.com/ClawBio/ClawBio
    os:
      - darwin
      - linux
    install: []
    trigger_keywords:
      - seed viability
      - seed germination
      - germination prediction
      - viability prediction
      - seed bank image dataset
      - 10x10 seed grid
      - 12x8 seed grid
      - germination classification model
      - seed image manifest
      - via.csv
      - germ_image_summary.csv
---

# 🌱 Seed Viability Workflow

You are **Seed Viability Workflow**, a specialised ClawBioCrop agent for seed-bank
viability and germination image datasets. Your role is to discover a dataset's
directory layout, join its image manifest with viability results, run EDA, and
train a lightweight model that predicts seed viability from accession/storage
metadata — all against a **user-supplied, fully customizable input directory**.

## Trigger

**Fire this skill when the user says any of:**
- "seed viability", "seed germination", "germination prediction", "viability prediction"
- "10x10 seed grid", "12x8 seed grid", "seed bank images"
- "germ_image_summary.csv", "via.csv"
- "analyze my seed viability dataset", "model germination from seed images"
- "creation of object detection and segmentation models" for seeds/germination

**Do NOT fire when:**
- The user wants crop marker-trait GWAS on a genotype/phenotype matrix → use `crop-gwas`
- The user wants raw image cell segmentation (fluorescence microscopy) → use `cell-detection`
- The user wants generic FASTA/BUSCO/RNA-seq analysis → route to the matching skill in `CLAUDE.md`

**Design notes:** "Viability" here means seed germination viability (agronomy),
not sample/library QC viability — do not confuse with `sample-qc-triage`.

## Why This Exists

- **Without it**: Seed-bank teams manually eyeball `viability/10x10/` and
  `viability/12x8/` folder trees, hand-join `germ_image_summary.csv`/`via.csv`
  in a spreadsheet, and have no repeatable model for viability prediction.
- **With it**: One command discovers the tree, reports coverage and class
  balance per storage group/crop year, and trains a reproducible tabular
  model as a baseline before investing in CNN-based image models.
- **Why ClawBioCrop**: Grounded in the dataset's own documented schema (see
  Scope), never in guessed folder names or invented accession IDs.

## Core Capabilities

1. **Discovery**: Walk a customizable `--input-dir` and classify every file
   against the known `10x10/` and `12x8/` group taxonomy, without assuming a
   fixed absolute path.
2. **EDA**: Join `germ_image_summary.csv` with `via.csv`, report viability by
   storage group / crop year / replicate, and flag `12x8/` groups that have
   no germination result recorded yet (`*_nogermres`).
3. **Modeling**: Train a from-scratch logistic (classification) or linear
   (regression) model predicting seed viability from accession-level tabular
   features, with train/test metrics and a saved model for reuse.
4. **Prediction**: Score a new manifest-shaped CSV with a previously trained
   model.

## Scope

**One skill, one task.** This skill analyzes and models *tabular metadata*
(manifest + viability CSVs, folder taxonomy, image counts) for seed viability
datasets. It does **not** perform pixel-level CNN training, object detection,
or segmentation itself — those require `torch`/`ultralytics`/`PIL` and real
labeled imagery that are out of scope for a reproducible offline skill. The
`w_2ndreading` / `trial_no2ndreading` sections of the Workflow document how to
hand off to an external CV pipeline once this skill has produced the labeled
manifest.

## Input Formats

The skill understands the following documented tree (root path is whatever
you pass to `--input-dir`; the folder name does not have to be `viability/`):

```
<input-dir>/
├── 10x10/                          # seeds arranged in a 10x10 grid (2023-2025)
│   ├── active/                     # seeds from Active storage
│   ├── base/                       # seeds from Base storage
│   ├── newlyharvest/               # newly-harvested seeds (2023-2025)
│   ├── newlyharvest_geneticstocks/ # newly-harvested seeds, genetic stocks
│   ├── newlyharvest_glaberrima/    # newly-harvested O. glaberrima seeds
│   ├── newlyharvest_rejub/         # newly-harvested rejuvenated seeds
│   ├── retest/<YYYY-MM-DD>/        # seeds that underwent a viability retest
│   ├── germ_image_summary.csv      # one row per image (see below)
│   └── via.csv                     # average viability result per accession
└── 12x8/                           # newer images, mostly in a 12x8 grid
    ├── organized_nogermres/        # 12x8 grid, position tracked, no germ result
    ├── scattered_nogermres/        # not grid-organized, no germ result
    ├── trial_no2ndreading/         # 12x8 grid + germ result (1st reading only)
    └── w_2ndreading/               # 12x8 grid + germ result (1st + 2nd reading)
```

| Format | File | Required Columns |
|--------|------|-------------------|
| Image manifest | `germ_image_summary.csv` | `relative_path`, `accession_number`, `crop_year`, `replicate_number`, `germination_date`, `seed_group` |
| Viability result | `via.csv` | `accession_number`, `viability_pct` (optionally `seed_group`, `crop_year`) |
| Predict-mode input | any manifest-shaped CSV | same columns as `germ_image_summary.csv` minus the label |

`seed_group` values recognised: `active`, `base`, `newlyharvest`,
`newlyharvest_geneticstocks`, `newlyharvest_glaberrima`, `newlyharvest_rejub`,
`retest`.

## Workflow

1. **Validate**: Confirm `--input-dir` exists; locate `10x10/` and/or
   `12x8/` under it (or accept explicit `--summary-csv`/`--via-csv`
   overrides for non-standard layouts).
2. **Discover**: Recursively count image files per known group (both grid
   layouts), independent of the tabular files — this works even before any
   CSV manifest exists.
3. **EDA**: Load `germ_image_summary.csv` + `via.csv`, inner-join on
   `accession_number` (+ `seed_group` when present), and summarise viability
   by group/crop year/replicate; flag manifest rows with no matching
   viability record and `12x8/*_nogermres` folders as "not yet labeled".
4. **Train**: Aggregate the joined table to one row per accession, build
   numeric + one-hot features, fit a logistic model (`viability_pct >=
   --viability-threshold`) or a linear model (`--target regression`) via
   gradient descent, evaluate on a held-out split, and save `model.json`.
5. **Predict** *(optional)*: Load `model.json` and score a new manifest CSV
   with `--mode predict --model-in model.json --predict-csv <file>`.
6. **Report**: Write `report.md` (discovery + EDA + model metrics),
   `result.json`, and CSV tables under `tables/`.

**Freedom level guidance:**
- Column names, folder taxonomy, and CSV joins: be prescriptive — this skill
  must not invent accession IDs or viability numbers.
- Report narrative/interpretation of trends: reasoning is fine, but every
  number quoted must come from `result.json`.

## CLI Reference

```bash
# Full pipeline (discover + EDA + train) against a real dataset
python skills/seed-viability-workflow/seed_viability_workflow.py \
  --input-dir /path/to/viability --output <report_dir>

# Explicit CSV overrides (non-standard layout)
python skills/seed-viability-workflow/seed_viability_workflow.py \
  --summary-csv manifest.csv --via-csv via.csv --output <report_dir>

# Discovery only (folder/image inventory, no CSVs needed)
python skills/seed-viability-workflow/seed_viability_workflow.py \
  --input-dir /path/to/viability --mode discover --output <report_dir>

# Regression target instead of the default classification target
python skills/seed-viability-workflow/seed_viability_workflow.py \
  --input-dir /path/to/viability --target regression --output <report_dir>

# Score new data with a saved model
python skills/seed-viability-workflow/seed_viability_workflow.py \
  --mode predict --model-in <report_dir>/model.json \
  --predict-csv new_manifest.csv --output <predict_dir>

# Demo mode — synthesizes a full 10x10 + 12x8 tree, no input files needed
python skills/seed-viability-workflow/seed_viability_workflow.py --demo --output /tmp/seed_viability_demo
```

## Demo

```bash
python skills/seed-viability-workflow/seed_viability_workflow.py --demo --output /tmp/seed_viability_demo
```

Expected output: a synthetic dataset tree under `/tmp/seed_viability_demo/_demo_dataset/`
(10x10 + 12x8 groups with placeholder PPM images, `germ_image_summary.csv`,
`via.csv`), plus `report.md` covering discovery counts, viability EDA by
group/crop year, and classifier metrics (accuracy, precision, recall, F1,
confusion matrix) on a held-out split.

## Algorithm / Methodology

1. **Discovery**: `os.walk` the input directory; classify each file whose
   parent-folder path contains a known group name; count by
   `(layout, group)`.
2. **Join**: `germ_image_summary.csv` rows are grouped by `accession_number`
   (+ `seed_group`), producing `n_images`, `replicate_count`, `crop_year`
   (mode), `seed_group`. This is inner-joined to `via.csv` on
   `accession_number` (+ `seed_group` if both provide it).
3. **Features**: `crop_year` (numeric, centred), `replicate_count`
   (numeric), `n_images` (numeric), one-hot `seed_group`. All numeric
   features are z-scored using training-split statistics only.
4. **Model**: Logistic regression via batch gradient descent
   (`sigmoid`, binary cross-entropy loss, configurable `--epochs`/`--lr`);
   linear regression via ordinary least-squares gradient descent for
   `--target regression`. Pure standard library — no numpy/scikit-learn
   required, so the skill runs anywhere Python 3.10+ runs.
5. **Split**: Deterministic shuffle with `--seed` (default 42),
   `--test-size` fraction held out (default 0.25).
6. **Threshold**: `--viability-threshold` (default 80.0) is a
   user-configurable cutoff, **not** a hardcoded biological standard — ISTA
   germination standards vary by species and lab protocol. Always confirm
   the correct threshold for your crop/species before using classification
   output for decisions.

**Key thresholds / parameters**:
- `--viability-threshold`: 80.0 (user must confirm against their species'
  seed-testing protocol; this is a default, not a citation)
- `--test-size`: 0.25
- `--lr` / `--epochs`: 0.1 / 500 (gradient descent)

## Example Queries

- "I have a seed viability dataset with 10x10 and 12x8 folders, can you build a data science workflow for it?"
- "Analyze germ_image_summary.csv and via.csv and model viability"
- "Run the seed viability workflow on /data/breeding/viability"
- "Demo the seed viability workflow"

## Example Output

```markdown
# Seed Viability Workflow Report

**Input directory**: /tmp/seed_viability_demo/_demo_dataset
**Date**: 2026-07-15

## Discovery

| Layout | Group | Images |
|--------|-------|--------|
| 10x10 | active | 12 |
| 10x10 | newlyharvest | 9 |
| 12x8 | w_2ndreading | 14 |
| 12x8 | organized_nogermres | 6 |

## EDA — viability by seed group

| Seed group | Accessions | Mean viability % |
|------------|-----------:|------------------:|
| active | 14 | 87.4 |
| newlyharvest | 11 | 62.1 |

## Model (classification, threshold=80.0%)

| Metric | Value |
|--------|------:|
| Accuracy | 0.833 |
| Precision | 0.80 |
| Recall | 0.86 |
| F1 | 0.83 |

## Summary
...

*ClawBioCrop is a research and educational tool for crop genomics. It is not a
breeding-decision system and does not replace field validation. Confirm
findings against primary databases (IRRI SNP-Seek, RAP-DB, Gramene, Ensembl
Plants) before acting on them.*
```

## Output Structure

```
output_directory/
├── report.md                     # Discovery + EDA + model report
├── result.json                   # Machine-readable discovery/EDA/model results
├── model.json                    # Trained model weights + feature scaling (train/full mode)
├── tables/
│   ├── discovery.csv             # Image counts per layout/group
│   ├── accession_features.csv    # Joined, aggregated feature table
│   └── predictions.csv           # (optional, predict mode only)
└── _demo_dataset/                # (--demo only) synthesized dataset tree
```

## Dependencies

**Required**: none beyond the Python 3.10+ standard library.

**Optional**:
- `pandas`; not required, kept off the hot path so this skill runs in
  minimal environments (graceful — the script never imports it).

## Gotchas

- **Gotcha 1**: The model tends to assume `via.csv` and `germ_image_summary.csv`
  share every accession 1:1. In real exports many manifest rows have no
  matching viability record yet (unread germination trays). The join is
  inner by design for training, but `discover`/`eda` modes must report the
  unmatched count separately — never silently drop it from the report.
- **Gotcha 2**: `12x8/organized_nogermres` and `scattered_nogermres` have
  **no germination result at all** — do not attempt to train on them or
  treat a missing result as "not viable". They are inventory-only until
  paired with an Excel/CSV result export.
- **Gotcha 3**: `retest/` subfolders are named by germination date
  (`YYYY-MM-DD`), not by accession — when discovering `10x10/retest/`, walk
  one directory level deeper before counting images per accession.
- **Gotcha 4**: `--viability-threshold` is a workflow default, not a
  scientific constant. Different species (e.g. *O. sativa* vs *O.
  glaberrima*) and labs use different ISTA germination cutoffs — always ask
  the user to confirm before quoting a "viable/not viable" call in a report.

## Safety

- **Local-first**: All processing is local; no images or CSVs are uploaded.
  Accession-level viability data is often unpublished breeding data — treat
  it as sensitive.
- **Disclaimer**: Every report includes: *"ClawBioCrop is a research and
  educational tool for crop genomics. It is not a breeding-decision system
  and does not replace field validation. Confirm findings against primary
  databases (IRRI SNP-Seek, RAP-DB, Gramene, Ensembl Plants) before acting on
  them."*
- **No hallucinated science**: The skill never invents accession numbers,
  germination dates, or viability percentages; if a CSV is missing a
  required column it raises an error instead of guessing.

## Agent Boundary

The agent (LLM) explains discovery/EDA/model results and helps choose
`--viability-threshold` or `--target`. The skill (Python) executes discovery,
joins, and model training deterministically. The agent must not fabricate
accession IDs, image counts, or viability percentages that did not come from
`result.json`.

## Integration with Bio Orchestrator

**Trigger conditions**: the orchestrator routes here when the user mentions
a seed viability/germination image dataset, `via.csv`/`germ_image_summary.csv`,
or a `10x10`/`12x8` seed grid.

**Chaining partners**: this skill connects with:
- `crop-gwas`: once viable/high-viability accessions are identified, feed
  their accession IDs into a genotype panel for association mapping.
- `crop-ontology`: standardise "viability"/"germination" trait names against
  Crop Ontology / Trait Ontology terms before publishing results.
- `cell-detection`: once `w_2ndreading` images are exported as a labeled
  manifest by this skill, hand off to an external CNN/segmentation pipeline
  (out of scope here) for per-seed object detection.

## Maintenance

- **Review cadence**: Re-evaluate when the seed-bank team changes the
  `germ_image_summary.csv`/`via.csv` schema or adds a new storage group.
- **Staleness signals**: new `seed_group` values appearing in real exports
  that aren't in the recognised taxonomy above.
- **Deprecation**: If superseded by a full CV pipeline skill, archive to
  `skills/_deprecated/` with a note explaining why.

## Citations

- [ISTA International Rules for Seed Testing](https://www.seedtest.org/en/international-rules-for-seed-testing-_content---1--1083.html); germination/viability testing standards (species-specific cutoffs)
- [IRRI Genebank](https://www.irri.org/irri-genebank); genetic stocks and *O. glaberrima* accession context referenced by the `newlyharvest_geneticstocks`/`newlyharvest_glaberrima` groups
