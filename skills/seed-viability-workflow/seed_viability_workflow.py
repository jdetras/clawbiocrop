#!/usr/bin/env python3
"""
seed_viability_workflow.py — Seed Viability & Germination Workflow (ClawBioCrop Skill)
=======================================================================================
Data-science workflow for seed-bank viability/germination image collections laid
out as documented `10x10/` (image manifest + per-accession viability CSVs) and
`12x8/` (newer grid images, partly labeled) directory trees. Discovers the tree
under a fully customizable --input-dir, joins the manifest with viability
results, runs EDA, and trains a from-scratch logistic/linear model to predict
seed viability from accession/storage metadata.

Usage:
    python seed_viability_workflow.py --input-dir /path/to/viability --output /tmp/report
    python seed_viability_workflow.py --input-dir /path/to/viability --mode discover --output /tmp/report
    python seed_viability_workflow.py --mode predict --model-in model.json \
        --predict-csv new_manifest.csv --output /tmp/predict
    python seed_viability_workflow.py --demo --output /tmp/seed_viability_demo

Pure standard library — no numpy/pandas/scikit-learn required.

ClawBioCrop is a research and educational tool for crop genomics, not a
breeding-decision system.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. It is not a "
    "breeding-decision system and does not replace field validation. Confirm findings "
    "against primary databases (IRRI SNP-Seek, RAP-DB, Gramene, Ensembl Plants) before "
    "acting on them."
)

TEN_BY_TEN_GROUPS = (
    "active",
    "base",
    "newlyharvest",
    "newlyharvest_geneticstocks",
    "newlyharvest_glaberrima",
    "newlyharvest_rejub",
    "retest",
)

TWELVE_BY_EIGHT_GROUPS = (
    "organized_nogermres",
    "scattered_nogermres",
    "trial_no2ndreading",
    "w_2ndreading",
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".ppm", ".bmp", ".gif"}

MANIFEST_REQUIRED_COLUMNS = [
    "relative_path",
    "accession_number",
    "crop_year",
    "replicate_number",
    "germination_date",
    "seed_group",
]
VIA_REQUIRED_COLUMNS = ["accession_number", "viability_pct"]

NUMERIC_FEATURES = ["crop_year", "replicate_count", "n_images"]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_dataset(root: Path) -> dict:
    """Walk root/10x10 and root/12x8, counting image files per known group."""
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"input directory not found: {root}")

    result = {"10x10": {}, "12x8": {}}
    layout_groups = {"10x10": TEN_BY_TEN_GROUPS, "12x8": TWELVE_BY_EIGHT_GROUPS}
    for layout, groups in layout_groups.items():
        layout_dir = root / layout
        if not layout_dir.exists():
            continue
        counts: dict[str, int] = {}
        for path in layout_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel_parts = path.relative_to(layout_dir).parts
            group = rel_parts[0] if rel_parts else "_other"
            if group not in groups:
                group = "_other"
            counts[group] = counts.get(group, 0) + 1
        result[layout] = counts
    return result


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _read_csv_checked(path: Path, required_columns: list[str]) -> list[dict]:
    path = Path(path)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing = [c for c in required_columns if c not in fieldnames]
        if missing:
            raise ValueError(
                f"missing required column(s) in {path.name}: {', '.join(missing)}"
            )
        return list(reader)


def load_manifest(path: Path) -> list[dict]:
    """Load germ_image_summary.csv (or a manifest-shaped CSV for --mode predict)."""
    return _read_csv_checked(path, MANIFEST_REQUIRED_COLUMNS)


def load_viability(path: Path) -> list[dict]:
    """Load via.csv; casts viability_pct to float."""
    rows = _read_csv_checked(path, VIA_REQUIRED_COLUMNS)
    for row in rows:
        row["viability_pct"] = float(row["viability_pct"])
    return rows


# ---------------------------------------------------------------------------
# Aggregation / join
# ---------------------------------------------------------------------------

def aggregate_accessions(manifest_rows: list[dict], via_rows: list[dict]):
    """Group manifest rows by (accession, seed_group) and join to via.csv.

    Returns (feature_rows, unmatched_manifest_groups, unmatched_via_rows).
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in manifest_rows:
        key = (row["accession_number"], row["seed_group"])
        groups[key].append(row)

    via_by_key: dict[tuple, dict] = {}
    via_by_acc_only: dict[str, list[dict]] = defaultdict(list)
    for via_row in via_rows:
        acc = via_row["accession_number"]
        grp = via_row.get("seed_group") or None
        if grp:
            via_by_key[(acc, grp)] = via_row
        else:
            via_by_acc_only[acc].append(via_row)

    matched_via_ids = set()
    feature_rows = []
    unmatched_manifest = 0
    for (acc, grp), items in groups.items():
        via_row = via_by_key.get((acc, grp))
        if via_row is None:
            candidates = via_by_acc_only.get(acc, [])
            if len(candidates) == 1:
                via_row = candidates[0]
        if via_row is None:
            unmatched_manifest += 1
            continue
        matched_via_ids.add(id(via_row))
        crop_years = [int(r["crop_year"]) for r in items if r.get("crop_year")]
        crop_year_mode = Counter(crop_years).most_common(1)[0][0] if crop_years else None
        replicate_numbers = {r.get("replicate_number") for r in items}
        feature_rows.append({
            "accession_number": acc,
            "seed_group": grp,
            "crop_year": crop_year_mode,
            "replicate_count": len(replicate_numbers),
            "n_images": len(items),
            "viability_pct": float(via_row["viability_pct"]),
        })

    unmatched_via = len(via_rows) - len(matched_via_ids)
    return feature_rows, unmatched_manifest, unmatched_via


def eda_summary(feature_rows: list[dict]) -> dict:
    by_group: dict[str, list[float]] = defaultdict(list)
    by_year: dict = defaultdict(list)
    for row in feature_rows:
        by_group[row["seed_group"]].append(row["viability_pct"])
        by_year[row["crop_year"]].append(row["viability_pct"])

    def summarize(d):
        return {
            str(k): {"n": len(v), "mean_viability_pct": round(sum(v) / len(v), 2)}
            for k, v in sorted(d.items(), key=lambda kv: str(kv[0]))
        }

    return {"by_seed_group": summarize(by_group), "by_crop_year": summarize(by_year)}


# ---------------------------------------------------------------------------
# Feature matrix
# ---------------------------------------------------------------------------

def build_design_matrix(feature_rows: list[dict], threshold: float = 80.0, target: str = "classification"):
    groups_seen = sorted({row["seed_group"] for row in feature_rows})
    feature_names = list(NUMERIC_FEATURES) + [f"seed_group={g}" for g in groups_seen]

    X = []
    for row in feature_rows:
        crop_year = float(row["crop_year"]) if row.get("crop_year") is not None else 0.0
        vec = [crop_year, float(row["replicate_count"]), float(row["n_images"])]
        vec += [1.0 if row["seed_group"] == g else 0.0 for g in groups_seen]
        X.append(vec)

    if target == "classification":
        y = [1.0 if row["viability_pct"] >= threshold else 0.0 for row in feature_rows]
    else:
        y = [float(row["viability_pct"]) for row in feature_rows]

    return X, y, feature_names, groups_seen


def train_test_split_indices(n: int, test_size: float = 0.25, seed: int = 42):
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    n_test = round(n * test_size)
    test_idx = sorted(idx[:n_test])
    train_idx = sorted(idx[n_test:])
    return train_idx, test_idx


def zscore_fit(X: list[list[float]], col_indices: list[int]):
    means, stds = {}, {}
    n = len(X)
    for c in col_indices:
        vals = [row[c] for row in X]
        mean = sum(vals) / n
        variance = sum((v - mean) ** 2 for v in vals) / n
        means[c] = mean
        stds[c] = variance ** 0.5 or 1.0
    return means, stds


def zscore_transform(X: list[list[float]], col_indices: list[int], means: dict, stds: dict):
    out = []
    for row in X:
        new_row = list(row)
        for c in col_indices:
            new_row[c] = (row[c] - means[c]) / stds[c]
        out.append(new_row)
    return out


def dot(row: list[float], weights: list[float]) -> float:
    return sum(r * w for r, w in zip(row, weights))


# ---------------------------------------------------------------------------
# Models (pure standard library)
# ---------------------------------------------------------------------------

def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _standardized_gradient_descent(X, y, lr, epochs, predict_fn, loss_grad_scale):
    """Shared GD loop: standardizes X internally, trains in z-space, and
    returns weights/bias converted back to the caller's original feature scale.
    """
    n_features = len(X[0]) if X else 0
    col_idx = list(range(n_features))
    means, stds = zscore_fit(X, col_idx)
    Xz = zscore_transform(X, col_idx, means, stds)

    weights = [0.0] * n_features
    bias = 0.0
    n = len(Xz)
    for _ in range(epochs):
        preds = [predict_fn(dot(row, weights) + bias) for row in Xz]
        errors = [p - t for p, t in zip(preds, y)]
        grad_w = [
            loss_grad_scale * sum(e * row[j] for e, row in zip(errors, Xz)) / n
            for j in range(n_features)
        ]
        grad_b = loss_grad_scale * sum(errors) / n
        weights = [w - lr * gw for w, gw in zip(weights, grad_w)]
        bias -= lr * grad_b

    orig_weights = [w / stds[j] for j, w in enumerate(weights)]
    orig_bias = bias - sum(w * means[j] / stds[j] for j, w in enumerate(weights))
    return orig_weights, orig_bias


def train_logistic(X: list[list[float]], y: list[float], lr: float = 0.1, epochs: int = 500):
    return _standardized_gradient_descent(X, y, lr, epochs, sigmoid, loss_grad_scale=1.0)


def predict_proba_logistic(X: list[list[float]], weights: list[float], bias: float):
    return [sigmoid(dot(row, weights) + bias) for row in X]


def train_linear(X: list[list[float]], y: list[float], lr: float = 0.1, epochs: int = 500):
    return _standardized_gradient_descent(X, y, lr, epochs, lambda z: z, loss_grad_scale=2.0)


def predict_linear(X: list[list[float]], weights: list[float], bias: float):
    return [dot(row, weights) + bias for row in X]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_classification(y_true: list[float], y_proba: list[float], threshold: float = 0.5) -> dict:
    preds = [1.0 if p >= threshold else 0.0 for p in y_proba]
    tp = sum(1 for t, p in zip(y_true, preds) if t == 1.0 and p == 1.0)
    tn = sum(1 for t, p in zip(y_true, preds) if t == 0.0 and p == 0.0)
    fp = sum(1 for t, p in zip(y_true, preds) if t == 0.0 and p == 1.0)
    fn = sum(1 for t, p in zip(y_true, preds) if t == 1.0 and p == 0.0)
    n = len(y_true)
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


def evaluate_regression(y_true: list[float], y_pred: list[float]) -> dict:
    n = len(y_true)
    errors = [p - t for p, t in zip(y_pred, y_true)]
    mse = sum(e * e for e in errors) / n
    rmse = mse ** 0.5
    mae = sum(abs(e) for e in errors) / n
    mean_y = sum(y_true) / n
    ss_tot = sum((t - mean_y) ** 2 for t in y_true)
    ss_res = sum(e * e for e in errors)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res == 0 else 0.0)
    return {"rmse": rmse, "mae": mae, "r2": r2}


# ---------------------------------------------------------------------------
# Demo data synthesis
# ---------------------------------------------------------------------------

def write_ppm(path: Path, width: int = 4, height: int = 4, seed: int = 0) -> None:
    """Write a tiny valid binary PPM (P6) placeholder image — no PIL dependency."""
    rng = random.Random(seed)
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    pixels = bytes(rng.randrange(0, 256) for _ in range(width * height * 3))
    Path(path).write_bytes(header + pixels)


_GROUP_BASE_VIABILITY = {
    "active": 90.0,
    "base": 85.0,
    "newlyharvest": 60.0,
    "newlyharvest_geneticstocks": 70.0,
    "newlyharvest_glaberrima": 68.0,
    "newlyharvest_rejub": 75.0,
    "retest": 55.0,
}


def synth_demo(root: Path, seed: int = 42, n_accessions_per_group: int = 6) -> None:
    """Synthesize a full 10x10 + 12x8 dataset tree matching the documented schema.

    All values are synthetic and reproducible from `seed`; they are not real
    seed-bank measurements.
    """
    root = Path(root)
    rng = random.Random(seed)
    crop_years = [2023, 2024, 2025]

    ten_dir = root / "10x10"
    manifest_rows = []
    via_rows = []
    counter = 0
    for group in TEN_BY_TEN_GROUPS:
        for _ in range(n_accessions_per_group):
            counter += 1
            acc = f"ACC{counter:04d}"
            crop_year = crop_years[counter % len(crop_years)]
            n_replicates = 1 + (counter % 2)
            month = (counter % 9) + 1
            germ_date = f"{crop_year}-{month:02d}-15"
            group_dir = ten_dir / group / germ_date if group == "retest" else ten_dir / group
            group_dir.mkdir(parents=True, exist_ok=True)
            for rep in range(1, n_replicates + 1):
                img_path = group_dir / f"{acc}_r{rep}.ppm"
                write_ppm(img_path, seed=counter * 10 + rep)
                manifest_rows.append({
                    "relative_path": img_path.relative_to(root).as_posix(),
                    "accession_number": acc,
                    "crop_year": str(crop_year),
                    "replicate_number": str(rep),
                    "germination_date": germ_date,
                    "seed_group": group,
                })
            viability = _GROUP_BASE_VIABILITY[group] + rng.gauss(0, 4)
            viability = max(0.0, min(100.0, viability))
            via_rows.append({
                "accession_number": acc,
                "seed_group": group,
                "crop_year": str(crop_year),
                "viability_pct": f"{viability:.2f}",
            })

    twelve_dir = root / "12x8"
    for group in TWELVE_BY_EIGHT_GROUPS:
        group_dir = twelve_dir / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for i in range(8):
            write_ppm(group_dir / f"img_{i:03d}.ppm", seed=1000 + i)

    with open(ten_dir / "germ_image_summary.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    with open(ten_dir / "via.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["accession_number", "seed_group", "crop_year", "viability_pct"])
        writer.writeheader()
        writer.writerows(via_rows)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _interpret(result: dict) -> str:
    parts = []
    discovery = result.get("discovery") or {}
    if discovery:
        total = sum(sum(g.values()) for g in discovery.values())
        parts.append(f"Discovered {total} image(s) across the recognised 10x10/12x8 taxonomy.")
    model = result.get("model")
    if model and model.get("metrics"):
        parts.append(
            "See the Model section above for held-out performance; confirm the "
            "viability threshold against your species' seed-testing protocol "
            "before treating classifications as ground truth."
        )
    if not parts:
        parts.append("Run in `full`/`train` mode with a populated 10x10/ dataset to see EDA and modeling results.")
    return " ".join(parts)


def generate_report(result: dict) -> str:
    lines = [
        "# Seed Viability Workflow Report",
        "",
        f"**Input directory**: {result.get('input_dir') or '(none — CSV overrides used)'}  ",
        f"**Mode**: {result.get('mode')}  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    discovery = result.get("discovery") or {}
    if discovery:
        lines += ["## Discovery", "", "| Layout | Seed group | Images |", "|--------|-----------|-------:|"]
        for layout, groups in discovery.items():
            for group, n in sorted(groups.items()):
                lines.append(f"| {layout} | {group} | {n} |")
        lines.append("")

    eda = result.get("eda")
    if eda:
        lines += [
            "## EDA — viability by seed group",
            "",
            "| Seed group | Accessions | Mean viability % |",
            "|------------|-----------:|------------------:|",
        ]
        for group, stats in eda.get("by_seed_group", {}).items():
            lines.append(f"| {group} | {stats['n']} | {stats['mean_viability_pct']} |")
        lines.append("")
        unmatched_manifest = result.get("unmatched_manifest_groups")
        unmatched_via = result.get("unmatched_via_rows")
        if unmatched_manifest is not None:
            lines.append(
                f"*{unmatched_manifest} manifest accession/group(s) had no matching via.csv row; "
                f"{unmatched_via} via.csv row(s) had no matching manifest images.*"
            )
            lines.append("")

    model = result.get("model")
    if model:
        meta, metrics = model["meta"], model["metrics"]
        lines += [
            f"## Model ({meta['target']}, threshold={meta['viability_threshold']}%)",
            "",
            f"Trained on {model['n_train']} accessions, evaluated on {model['n_test']} held out.",
            "",
        ]
        if metrics:
            lines += ["| Metric | Value |", "|--------|------:|"]
            for k, v in metrics.items():
                if k == "confusion_matrix":
                    continue
                lines.append(f"| {k} | {v:.3f} |" if isinstance(v, float) else f"| {k} | {v} |")
            lines.append("")

    if result.get("n_predictions") is not None:
        lines.append(f"## Predictions\n\nScored {result['n_predictions']} row(s). See `tables/predictions.csv`.\n")

    lines += ["## Summary", "", _interpret(result), "", "---", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(output_dir: Path, result: dict, feature_rows=None, model=None, predictions=None) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    discovery = result.get("discovery") or {}
    if discovery:
        with open(tables_dir / "discovery.csv", "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["layout", "seed_group", "n_images"])
            for layout, groups in discovery.items():
                for group, n in sorted(groups.items()):
                    writer.writerow([layout, group, n])

    if feature_rows:
        with open(tables_dir / "accession_features.csv", "w", newline="") as fh:
            fieldnames = ["accession_number", "seed_group", "crop_year", "replicate_count", "n_images", "viability_pct"]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(feature_rows)

    if predictions is not None:
        with open(tables_dir / "predictions.csv", "w", newline="") as fh:
            fieldnames = list(predictions[0].keys()) if predictions else []
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(predictions)

    if model is not None:
        (output_dir / "model.json").write_text(json.dumps(model, indent=2))

    (output_dir / "report.md").write_text(generate_report(result))
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"[seed-viability-workflow] wrote {output_dir / 'report.md'}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_predict(args) -> dict:
    model = json.loads(Path(args.model_in).read_text())
    rows = load_manifest(Path(args.predict_csv))
    feature_names = model["feature_names"]
    groups_seen = model["groups_seen"]
    weights = model["weights"]
    bias = model["bias"]
    target = model["target"]

    predictions = []
    for row in rows:
        crop_year = float(row["crop_year"]) if row.get("crop_year") else 0.0
        replicate_count = float(row.get("replicate_number") or 1)
        n_images = 1.0
        feat = [crop_year, replicate_count, n_images]
        feat += [1.0 if row.get("seed_group") == g else 0.0 for g in groups_seen]
        pred_row = dict(row)
        if target == "classification":
            proba = sigmoid(dot(feat, weights) + bias)
            pred_row["predicted_viability_proba"] = round(proba, 4)
            pred_row["predicted_label"] = int(proba >= 0.5)
        else:
            pred_row["predicted_viability_pct"] = round(dot(feat, weights) + bias, 2)
        predictions.append(pred_row)

    result = {
        "skill": "seed-viability-workflow",
        "mode": "predict",
        "model_in": str(args.model_in),
        "n_predictions": len(predictions),
        "feature_names": feature_names,
        "disclaimer": DISCLAIMER,
    }
    write_outputs(args.output, result, predictions=predictions)
    return result


def execute(args) -> dict:
    if args.demo:
        demo_root = Path(args.output) / "_demo_dataset"
        synth_demo(demo_root, seed=args.seed)
        input_dir = demo_root
        mode = "full"
    else:
        mode = args.mode
        input_dir = args.input_dir

    if mode == "predict":
        if not args.model_in or not args.predict_csv:
            raise ValueError("--mode predict requires --model-in and --predict-csv")
        return run_predict(args)

    if input_dir is None and not (args.summary_csv or args.via_csv):
        raise ValueError("provide --input-dir (or --summary-csv/--via-csv), or use --demo")

    if input_dir is not None and not Path(input_dir).exists():
        raise FileNotFoundError(f"input directory not found: {input_dir}")

    discovery = discover_dataset(Path(input_dir)) if input_dir is not None else {}

    result = {
        "skill": "seed-viability-workflow",
        "mode": mode,
        "input_dir": str(input_dir) if input_dir else None,
        "discovery": discovery,
        "disclaimer": DISCLAIMER,
    }

    if mode == "discover":
        write_outputs(args.output, result)
        return result

    summary_csv = args.summary_csv or (Path(input_dir) / "10x10" / "germ_image_summary.csv" if input_dir else None)
    via_csv = args.via_csv or (Path(input_dir) / "10x10" / "via.csv" if input_dir else None)
    if not summary_csv or not via_csv or not Path(summary_csv).exists() or not Path(via_csv).exists():
        raise FileNotFoundError(
            "germ_image_summary.csv / via.csv not found; pass --summary-csv/--via-csv "
            "or --input-dir with a 10x10/ subfolder"
        )

    manifest_rows = load_manifest(Path(summary_csv))
    via_rows = load_viability(Path(via_csv))
    feature_rows, unmatched_manifest, unmatched_via = aggregate_accessions(manifest_rows, via_rows)

    result["eda"] = eda_summary(feature_rows)
    result["unmatched_manifest_groups"] = unmatched_manifest
    result["unmatched_via_rows"] = unmatched_via
    result["n_accessions"] = len(feature_rows)

    if mode == "eda":
        write_outputs(args.output, result, feature_rows=feature_rows)
        return result

    if mode not in ("train", "full"):
        raise ValueError(f"unknown mode: {mode}")

    if len(feature_rows) < 4:
        raise ValueError("need at least 4 accessions with matched viability results to train a model")

    X, y, feature_names, groups_seen = build_design_matrix(
        feature_rows, threshold=args.viability_threshold, target=args.target
    )
    train_idx, test_idx = train_test_split_indices(len(X), test_size=args.test_size, seed=args.seed)
    X_train, y_train = [X[i] for i in train_idx], [y[i] for i in train_idx]
    X_test, y_test = [X[i] for i in test_idx], [y[i] for i in test_idx]

    if args.target == "classification":
        weights, bias = train_logistic(X_train, y_train, lr=args.lr, epochs=args.epochs)
        metrics = evaluate_classification(y_test, predict_proba_logistic(X_test, weights, bias)) if X_test else {}
    else:
        weights, bias = train_linear(X_train, y_train, lr=args.lr, epochs=args.epochs)
        metrics = evaluate_regression(y_test, predict_linear(X_test, weights, bias)) if X_test else {}

    model = {
        "target": args.target,
        "feature_names": feature_names,
        "groups_seen": groups_seen,
        "weights": weights,
        "bias": bias,
        "viability_threshold": args.viability_threshold,
    }
    result["model"] = {"meta": model, "metrics": metrics, "n_train": len(X_train), "n_test": len(X_test)}
    write_outputs(args.output, result, feature_rows=feature_rows, model=model)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seed viability & germination data-science workflow (ClawBioCrop)")
    p.add_argument("--input-dir", type=Path, help="Root of viability dataset (contains 10x10/ and/or 12x8/)")
    p.add_argument("--summary-csv", type=Path, help="Override path to germ_image_summary.csv")
    p.add_argument("--via-csv", type=Path, help="Override path to via.csv")
    p.add_argument("--output", type=Path, default=Path("seed_viability_workflow_out"), help="Output directory")
    p.add_argument("--mode", choices=["discover", "eda", "train", "predict", "full"], default="full")
    p.add_argument("--target", choices=["classification", "regression"], default="classification")
    p.add_argument("--viability-threshold", type=float, default=80.0)
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--lr", type=float, default=0.1)
    p.add_argument("--epochs", type=int, default=500)
    p.add_argument("--model-in", type=Path, help="Path to model.json for --mode predict")
    p.add_argument("--predict-csv", type=Path, help="Manifest-shaped CSV to score in --mode predict")
    p.add_argument("--demo", action="store_true", help="Synthesize a demo dataset and run the full pipeline")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        execute(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
