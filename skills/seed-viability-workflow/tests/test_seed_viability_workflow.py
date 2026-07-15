"""Tests for seed-viability-workflow. Red/green TDD.

These tests define the expected behaviour of the seed viability data-science
workflow (directory discovery over a customizable --input-dir, manifest/via
CSV joins, EDA, and a from-scratch logistic/linear model) before the
implementation exists.
"""

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "seed_viability_workflow.py"

sys.path.insert(0, str(SKILL_DIR))

import seed_viability_workflow as svw  # noqa: E402


DISCLAIMER_SNIPPET = "not a breeding-decision system"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscoverDataset:
    def _make_tree(self, root: Path):
        for group in ("active", "newlyharvest"):
            d = root / "10x10" / group
            d.mkdir(parents=True)
            for i in range(3):
                svw.write_ppm(d / f"img_{i}.ppm")
        retest_dir = root / "10x10" / "retest" / "2024-05-01"
        retest_dir.mkdir(parents=True)
        svw.write_ppm(retest_dir / "img_0.ppm")
        for group in ("organized_nogermres", "w_2ndreading"):
            d = root / "12x8" / group
            d.mkdir(parents=True)
            for i in range(2):
                svw.write_ppm(d / f"img_{i}.ppm")
        # a non-image file should never be counted
        (root / "10x10" / "active" / "notes.txt").write_text("not an image")

    def test_counts_per_group(self, tmp_path):
        self._make_tree(tmp_path)
        result = svw.discover_dataset(tmp_path)
        assert result["10x10"]["active"] == 3
        assert result["10x10"]["newlyharvest"] == 3
        assert result["12x8"]["organized_nogermres"] == 2
        assert result["12x8"]["w_2ndreading"] == 2

    def test_retest_nested_by_date_still_counted(self, tmp_path):
        self._make_tree(tmp_path)
        result = svw.discover_dataset(tmp_path)
        assert result["10x10"]["retest"] == 1

    def test_missing_layout_is_zero_not_error(self, tmp_path):
        (tmp_path / "10x10" / "active").mkdir(parents=True)
        svw.write_ppm(tmp_path / "10x10" / "active" / "a.ppm")
        result = svw.discover_dataset(tmp_path)
        assert result["12x8"] == {}

    def test_nonexistent_root_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            svw.discover_dataset(tmp_path / "does_not_exist")

    def test_non_image_files_not_counted(self, tmp_path):
        self._make_tree(tmp_path)
        result = svw.discover_dataset(tmp_path)
        total = sum(result["10x10"].values()) + sum(result["12x8"].values())
        assert total == 3 + 3 + 1 + 2 + 2  # notes.txt excluded


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_loads_valid_manifest(self, tmp_path):
        p = tmp_path / "germ_image_summary.csv"
        p.write_text(
            "relative_path,accession_number,crop_year,replicate_number,"
            "germination_date,seed_group\n"
            "10x10/active/a1_r1.ppm,ACC001,2024,1,2024-05-01,active\n"
        )
        rows = svw.load_manifest(p)
        assert len(rows) == 1
        assert rows[0]["accession_number"] == "ACC001"

    def test_missing_required_column_raises(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("relative_path,accession_number\nfoo.ppm,ACC001\n")
        with pytest.raises(ValueError, match="missing required column"):
            svw.load_manifest(p)


class TestLoadViability:
    def test_loads_valid_via(self, tmp_path):
        p = tmp_path / "via.csv"
        p.write_text("accession_number,seed_group,viability_pct\nACC001,active,91.5\n")
        rows = svw.load_viability(p)
        assert rows[0]["viability_pct"] == 91.5

    def test_missing_required_column_raises(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("accession_number\nACC001\n")
        with pytest.raises(ValueError, match="missing required column"):
            svw.load_viability(p)


# ---------------------------------------------------------------------------
# Aggregation / join
# ---------------------------------------------------------------------------


class TestAggregateAccessions:
    def _manifest(self):
        return [
            {"relative_path": "a", "accession_number": "ACC001", "crop_year": "2024",
             "replicate_number": "1", "germination_date": "2024-05-01", "seed_group": "active"},
            {"relative_path": "b", "accession_number": "ACC001", "crop_year": "2024",
             "replicate_number": "2", "germination_date": "2024-05-01", "seed_group": "active"},
            {"relative_path": "c", "accession_number": "ACC002", "crop_year": "2023",
             "replicate_number": "1", "germination_date": "2023-05-01", "seed_group": "newlyharvest"},
        ]

    def _via(self):
        return [
            {"accession_number": "ACC001", "seed_group": "active", "viability_pct": "92.0"},
            {"accession_number": "ACC999", "seed_group": "active", "viability_pct": "50.0"},
        ]

    def test_join_matches_by_accession_and_group(self):
        rows, unmatched_manifest, unmatched_via = svw.aggregate_accessions(self._manifest(), self._via())
        assert len(rows) == 1
        row = rows[0]
        assert row["accession_number"] == "ACC001"
        assert row["n_images"] == 2
        assert row["viability_pct"] == 92.0
        assert row["crop_year"] == 2024

    def test_unmatched_counts_reported(self):
        rows, unmatched_manifest, unmatched_via = svw.aggregate_accessions(self._manifest(), self._via())
        assert unmatched_manifest == 1  # ACC002 has no via.csv row
        assert unmatched_via == 1  # ACC999 has no manifest row


# ---------------------------------------------------------------------------
# Feature matrix / modeling
# ---------------------------------------------------------------------------


def _feature_rows():
    rows = []
    groups = ["active"] * 8 + ["newlyharvest"] * 8
    for i, g in enumerate(groups):
        base = 90.0 if g == "active" else 55.0
        via = base + (i % 3)
        rows.append({
            "accession_number": f"ACC{i:03d}",
            "seed_group": g,
            "crop_year": 2023 + (i % 3),
            "replicate_count": 1 + (i % 2),
            "n_images": 2 + (i % 3),
            "viability_pct": via,
        })
    return rows


class TestBuildDesignMatrix:
    def test_classification_labels_are_binary(self):
        X, y, feature_names, groups_seen = svw.build_design_matrix(
            _feature_rows(), threshold=80.0, target="classification"
        )
        assert set(y) <= {0.0, 1.0}
        assert len(X) == len(y) == 16
        assert "seed_group=active" in feature_names

    def test_regression_labels_are_continuous(self):
        X, y, feature_names, groups_seen = svw.build_design_matrix(
            _feature_rows(), target="regression"
        )
        assert any(v not in (0.0, 1.0) for v in y)

    def test_row_width_matches_feature_names(self):
        X, y, feature_names, groups_seen = svw.build_design_matrix(_feature_rows())
        assert all(len(row) == len(feature_names) for row in X)


class TestSplitAndScale:
    def test_split_is_deterministic(self):
        a = svw.train_test_split_indices(20, test_size=0.25, seed=7)
        b = svw.train_test_split_indices(20, test_size=0.25, seed=7)
        assert a == b

    def test_split_sizes(self):
        train_idx, test_idx = svw.train_test_split_indices(20, test_size=0.25, seed=7)
        assert len(test_idx) == 5
        assert len(train_idx) == 15
        assert set(train_idx).isdisjoint(test_idx)

    def test_zscore_roundtrip_mean_zero(self):
        X = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]
        means, stds = svw.zscore_fit(X, [0, 1])
        Xz = svw.zscore_transform(X, [0, 1], means, stds)
        col0 = [row[0] for row in Xz]
        assert abs(sum(col0) / len(col0)) < 1e-9


class TestLogisticRegression:
    def test_learns_separable_data(self):
        X = [[0.0], [0.0], [0.0], [10.0], [10.0], [10.0]]
        y = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
        weights, bias = svw.train_logistic(X, y, lr=0.5, epochs=1000)
        proba = svw.predict_proba_logistic(X, weights, bias)
        preds = [1.0 if p >= 0.5 else 0.0 for p in proba]
        assert preds == y

    def test_sigmoid_bounds(self):
        assert 0.0 < svw.sigmoid(-100) < 1e-6
        assert 0.999999 < svw.sigmoid(100) <= 1.0
        assert svw.sigmoid(0.0) == pytest.approx(0.5)


class TestLinearRegression:
    def test_recovers_linear_relationship(self):
        X = [[float(i)] for i in range(20)]
        y = [3.0 * x[0] + 2.0 for x in X]
        weights, bias = svw.train_linear(X, y, lr=0.01, epochs=2000)
        preds = svw.predict_linear(X, weights, bias)
        rmse = (sum((p - t) ** 2 for p, t in zip(preds, y)) / len(y)) ** 0.5
        assert rmse < 1.0


class TestEvaluation:
    def test_evaluate_classification_perfect(self):
        y_true = [0.0, 0.0, 1.0, 1.0]
        y_proba = [0.1, 0.2, 0.9, 0.8]
        metrics = svw.evaluate_classification(y_true, y_proba, threshold=0.5)
        assert metrics["accuracy"] == 1.0
        assert metrics["confusion_matrix"]["tp"] == 2
        assert metrics["confusion_matrix"]["tn"] == 2

    def test_evaluate_regression_perfect(self):
        y_true = [1.0, 2.0, 3.0]
        y_pred = [1.0, 2.0, 3.0]
        metrics = svw.evaluate_regression(y_true, y_pred)
        assert metrics["rmse"] == 0.0
        assert metrics["r2"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Demo synthesis
# ---------------------------------------------------------------------------


class TestSynthDemo:
    def test_creates_expected_tree(self, tmp_path):
        svw.synth_demo(tmp_path, seed=1)
        assert (tmp_path / "10x10" / "germ_image_summary.csv").exists()
        assert (tmp_path / "10x10" / "via.csv").exists()
        for group in svw.TEN_BY_TEN_GROUPS:
            if group == "retest":
                continue
            assert (tmp_path / "10x10" / group).is_dir()
        for group in svw.TWELVE_BY_EIGHT_GROUPS:
            assert (tmp_path / "12x8" / group).is_dir()

    def test_manifest_rows_match_written_images(self, tmp_path):
        svw.synth_demo(tmp_path, seed=1)
        rows = svw.load_manifest(tmp_path / "10x10" / "germ_image_summary.csv")
        discovery = svw.discover_dataset(tmp_path)
        assert len(rows) == sum(discovery["10x10"].values())

    def test_reproducible_with_same_seed(self, tmp_path):
        out1, out2 = tmp_path / "a", tmp_path / "b"
        svw.synth_demo(out1, seed=5)
        svw.synth_demo(out2, seed=5)
        rows1 = svw.load_viability(out1 / "10x10" / "via.csv")
        rows2 = svw.load_viability(out2 / "10x10" / "via.csv")
        assert rows1 == rows2


# ---------------------------------------------------------------------------
# CLI / end-to-end
# ---------------------------------------------------------------------------


class TestCLI:
    def test_no_args_exits_nonzero(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        assert result.returncode != 0

    def test_demo_mode_produces_output(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "model.json").exists()
        assert (tmp_path / "tables" / "discovery.csv").exists()
        assert (tmp_path / "tables" / "accession_features.csv").exists()

    def test_discover_mode_with_custom_input_dir(self, tmp_path):
        dataset_dir = tmp_path / "my_custom_dataset_location"
        svw.synth_demo(dataset_dir, seed=2)
        out_dir = tmp_path / "out"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--input-dir", str(dataset_dir),
             "--mode", "discover", "--output", str(out_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = json.loads((out_dir / "result.json").read_text())
        assert payload["discovery"]["10x10"]["active"] > 0

    def test_missing_input_dir_exits_nonzero(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--input-dir", str(tmp_path / "nope"),
             "--output", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_predict_mode_round_trip(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        svw.synth_demo(dataset_dir, seed=3)
        train_out = tmp_path / "train_out"
        r1 = subprocess.run(
            [sys.executable, str(SCRIPT), "--input-dir", str(dataset_dir),
             "--mode", "train", "--output", str(train_out)],
            capture_output=True, text=True,
        )
        assert r1.returncode == 0, f"stderr: {r1.stderr}"
        predict_out = tmp_path / "predict_out"
        r2 = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "predict",
             "--model-in", str(train_out / "model.json"),
             "--predict-csv", str(dataset_dir / "10x10" / "germ_image_summary.csv"),
             "--output", str(predict_out)],
            capture_output=True, text=True,
        )
        assert r2.returncode == 0, f"stderr: {r2.stderr}"
        with open(predict_out / "tables" / "predictions.csv") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) > 0
        assert "predicted_viability_pct" in rows[0] or "predicted_label" in rows[0]


class TestOutputFormat:
    def test_result_json_is_valid(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True,
        )
        result = json.loads((tmp_path / "result.json").read_text())
        assert result["skill"] == "seed-viability-workflow"

    def test_report_contains_disclaimer(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPT), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True,
        )
        report = (tmp_path / "report.md").read_text()
        assert DISCLAIMER_SNIPPET in report


class TestDemoData:
    def test_demo_examples_exist(self):
        assert (SKILL_DIR / "examples" / "demo_germ_image_summary.csv").exists()
        assert (SKILL_DIR / "examples" / "demo_via.csv").exists()


def _parse_output_contract(skill_md):
    """Extract files promised in the SKILL.md '## Output Structure' tree."""
    if not skill_md.exists():
        return []
    text = skill_md.read_text()
    m = re.search(r"##\s*Output Structure\s*\n+```[^\n]*\n(.*?)\n```", text, re.S)
    if not m:
        return []
    files = []
    parents = {}
    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        parts = re.split(r"\s+#", raw, maxsplit=1)
        entry, comment = parts[0], (parts[1] if len(parts) > 1 else "")
        mm = re.match(r"^([\s│├└─]*)(.*)$", entry)
        prefix, name = mm.group(1), mm.group(2).strip()
        if not name:
            continue
        depth = len(prefix) // 4
        if depth == 0:
            continue
        if name.endswith("/"):
            parents[depth] = name.rstrip("/")
            for d in [k for k in parents if k > depth]:
                del parents[d]
            continue
        if "optional" in comment.lower():
            continue
        rel = "/".join(parents[d] for d in sorted(parents) if d < depth)
        files.append(rel + "/" + name if rel else name)
    return files


class TestOutputContract:
    def test_documented_outputs_are_produced(self, tmp_path):
        promised = _parse_output_contract(SKILL_DIR / "SKILL.md")
        if not promised:
            pytest.skip("No parseable '## Output Structure' section in SKILL.md")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"demo run failed: {result.stderr}"
        missing = [p for p in promised if not (tmp_path / p).exists()]
        assert not missing, (
            "SKILL.md Output Structure promises artifacts the skill did not "
            "produce: " + ", ".join(missing)
        )
