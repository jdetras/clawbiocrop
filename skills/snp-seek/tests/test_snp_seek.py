"""Tests for snp-seek — IRRI SNP-Seek rice variant explorer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snp_seek import (
    DEMO_SNPS,
    VARIETAL_GROUPS,
    parse_region,
    resolve_locus,
    query_region,
    summarise_groups,
    generate_report,
    write_outputs,
    main,
)


class TestDemoData:
    def test_non_empty(self):
        assert len(DEMO_SNPS) > 0

    def test_required_keys(self):
        for s in DEMO_SNPS:
            for k in ("snp_id", "chrom", "pos", "ref", "alt", "locus", "effect", "maf", "group_alt_freq"):
                assert k in s

    def test_group_freqs_cover_all_groups(self):
        for s in DEMO_SNPS:
            for g in VARIETAL_GROUPS:
                assert g in s["group_alt_freq"]


class TestParsing:
    def test_parse_region(self):
        assert parse_region("chr01:1000000-1010000") == ("chr01", 1000000, 1010000)

    def test_parse_region_invalid(self):
        with pytest.raises(ValueError):
            parse_region("chr01-bad")

    def test_resolve_locus(self):
        chrom, start, end = resolve_locus("LOC_Os01g01010")
        assert chrom == "chr01"
        assert start < end

    def test_resolve_locus_unknown(self):
        with pytest.raises(ValueError):
            resolve_locus("LOC_Os99g99999")


class TestQuery:
    def test_query_region_finds_snps(self):
        hits = query_region("chr01", 1000000, 1010000)
        assert len(hits) == len(DEMO_SNPS)

    def test_query_region_subset(self):
        hits = query_region("chr01", 1000000, 1002000)
        assert all(1000000 <= s["pos"] <= 1002000 for s in hits)
        assert len(hits) >= 1

    def test_query_region_sorted(self):
        hits = query_region("chr01", 1000000, 1010000)
        positions = [s["pos"] for s in hits]
        assert positions == sorted(positions)

    def test_query_empty_region(self):
        assert query_region("chr12", 1, 100) == []

    def test_summarise_groups(self):
        hits = query_region("chr01", 1000000, 1010000)
        summary = summarise_groups(hits)
        assert set(summary.keys()) == set(VARIETAL_GROUPS)
        assert all(0.0 <= v <= 1.0 for v in summary.values())


class TestReport:
    def test_report_contains_region(self):
        hits = query_region("chr01", 1000000, 1010000)
        md = generate_report("chr01", 1000000, 1010000, hits)
        assert "SNP-Seek" in md
        assert "3K-RGP" in md
        assert "indica" in md

    def test_report_has_disclaimer(self):
        hits = query_region("chr01", 1000000, 1010000)
        md = generate_report("chr01", 1000000, 1010000, hits)
        assert "ClawBioCrop is a research" in md

    def test_report_empty(self):
        md = generate_report("chr12", 1, 100, [])
        assert "No SNPs" in md


class TestOutputs:
    def test_write_outputs(self, tmp_path):
        hits = query_region("chr01", 1000000, 1010000)
        md = generate_report("chr01", 1000000, 1010000, hits)
        write_outputs(tmp_path, md, hits, {"n_snps": len(hits)})
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "tables" / "snps.csv").exists()
        result = json.loads((tmp_path / "result.json").read_text())
        assert result["meta"]["n_snps"] == len(hits)


class TestDemoMode:
    def test_demo_runs(self, tmp_path):
        rc = main(["--demo", "--output", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "report.md").exists()

    def test_locus_mode(self, tmp_path):
        rc = main(["--locus", "LOC_Os01g01010", "--output", str(tmp_path)])
        assert rc == 0
        report = (tmp_path / "report.md").read_text()
        assert "LOC_Os01g01010" in report
