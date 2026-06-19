"""Tests for crop-gwas — crop GWAS association scan."""

import csv
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crop_gwas import (
    linreg_pvalue,
    lambda_gc,
    parse_snp_id,
    run_gwas,
    synth_demo,
    generate_report,
    write_outputs,
    main,
)


class TestStats:
    def test_linreg_perfect_correlation(self):
        x = [0, 1, 2, 0, 1, 2, 0, 1, 2]
        y = [v * 3.0 for v in x]
        beta, r, p, n = linreg_pvalue(x, y)
        assert abs(beta - 3.0) < 1e-6
        assert r > 0.99
        assert p < 0.05

    def test_linreg_no_correlation(self):
        x = [0, 1, 2, 0, 1, 2]
        y = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        beta, r, p, n = linreg_pvalue(x, y)
        assert p == 1.0

    def test_linreg_too_few(self):
        assert linreg_pvalue([1], [1])[2] == 1.0

    def test_lambda_gc_null_near_one(self):
        # Uniform p-values -> lambda_GC near 1.0
        ps = [(i + 0.5) / 1000 for i in range(1000)]
        lam = lambda_gc(ps)
        assert 0.8 < lam < 1.2

    def test_parse_snp_id(self):
        assert parse_snp_id("chr01:1000123") == ("chr01", 1000123)
        assert parse_snp_id("rsX")[1] == 0


class TestGWAS:
    def test_demo_recovers_causal(self):
        geno, pheno, trait, causal = synth_demo()
        results, meta = run_gwas(geno, pheno, trait)
        assert meta["n_snps"] == 200
        assert meta["n_samples"] == 300
        sig = {d["snp"] for d in results if d["significant"]}
        # At least one planted causal SNP should be recovered as significant.
        assert len(set(causal) & sig) >= 1

    def test_results_sorted_by_p(self):
        geno, pheno, trait, _ = synth_demo()
        results, _ = run_gwas(geno, pheno, trait)
        ps = [d["p"] for d in results]
        assert ps == sorted(ps)

    def test_no_overlap_raises(self):
        geno = [{"sample": "A", "chr01:1": "0"}]
        pheno = [{"sample": "B", "t": "1"}]
        with pytest.raises(ValueError):
            run_gwas(geno, pheno, "t")

    def test_missing_trait_raises(self):
        geno = [{"sample": "A", "chr01:1": "0"}, {"sample": "B", "chr01:1": "1"},
                {"sample": "C", "chr01:1": "2"}]
        pheno = [{"sample": "A", "t": "1"}, {"sample": "B", "t": "x"},
                 {"sample": "C", "t": "3"}]
        with pytest.raises(ValueError):
            run_gwas(geno, pheno, "t")


class TestReportAndCLI:
    def test_report_content(self):
        geno, pheno, trait, causal = synth_demo()
        results, meta = run_gwas(geno, pheno, trait)
        md = generate_report(results, meta, causal=causal)
        assert "Crop GWAS Association Report" in md
        assert "lambda_GC" in md
        assert "ClawBioCrop is a research" in md
        assert "Demo ground truth" in md

    def test_write_outputs(self, tmp_path):
        geno, pheno, trait, causal = synth_demo()
        results, meta = run_gwas(geno, pheno, trait)
        write_outputs(tmp_path, generate_report(results, meta, causal), results, meta)
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "tables" / "associations.csv").exists()
        data = json.loads((tmp_path / "result.json").read_text())
        assert data["meta"]["n_snps"] == 200

    def test_demo_cli(self, tmp_path):
        rc = main(["--demo", "--output", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "report.md").exists()

    def test_file_cli(self, tmp_path):
        geno, pheno, trait, _ = synth_demo(n_samples=50, n_snps=20, n_causal=2)
        gpath = tmp_path / "geno.csv"
        ppath = tmp_path / "pheno.csv"
        with open(gpath, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(geno[0].keys()))
            w.writeheader()
            w.writerows(geno)
        with open(ppath, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["sample", trait])
            w.writeheader()
            w.writerows(pheno)
        rc = main(["--genotypes", str(gpath), "--phenotype", str(ppath),
                   "--trait", trait, "--output", str(tmp_path / "out")])
        assert rc == 0
        assert (tmp_path / "out" / "report.md").exists()
