"""Tests for rice-pilaf — post-GWAS/QTL browser for rice."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rice_pilaf import (
    GENE_MODELS,
    parse_loci,
    parse_bed,
    candidate_genes,
    enrichment_summary,
    prioritise,
    generate_report,
    write_outputs,
    main,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestParsing:
    def test_parse_loci(self):
        ivs = parse_loci("chr01:1000000-1010000,chr03:200000-260000")
        assert len(ivs) == 2
        assert ivs[0] == {"chrom": "chr01", "start": 1000000, "end": 1010000}

    def test_parse_loci_empty(self):
        with pytest.raises(ValueError):
            parse_loci(",")

    def test_parse_bed(self):
        ivs = parse_bed(EXAMPLES / "demo_peaks.bed")
        assert len(ivs) == 3
        assert ivs[0]["chrom"] == "chr01"


class TestCandidateGenes:
    def test_overlap_detection(self):
        ivs = [{"chrom": "chr01", "start": 1000000, "end": 1010000}]
        hits = candidate_genes(ivs)
        genes = {g["gene"] for g in hits}
        assert "LOC_Os01g01010" in genes
        assert "LOC_Os01g01040" in genes

    def test_no_overlap(self):
        ivs = [{"chrom": "chr12", "start": 1, "end": 100}]
        assert candidate_genes(ivs) == []

    def test_dedup_across_intervals(self):
        ivs = [
            {"chrom": "chr01", "start": 1000000, "end": 1010000},
            {"chrom": "chr01", "start": 1000500, "end": 1001500},
        ]
        hits = candidate_genes(ivs)
        gene_ids = [g["gene"] for g in hits]
        assert len(gene_ids) == len(set(gene_ids))

    def test_source_locus_tagged(self):
        ivs = [{"chrom": "chr03", "start": 200000, "end": 260000}]
        hits = candidate_genes(ivs)
        assert all("source_locus" in g for g in hits)


class TestSummaries:
    def test_enrichment(self):
        ivs = parse_loci("chr01:1000000-1010000,chr03:200000-260000,chr07:5390000-5410000")
        hits = candidate_genes(ivs)
        enrich = enrichment_summary(hits)
        assert sum(enrich.values()) == len(hits)
        assert "yield" in enrich

    def test_prioritise_named_genes_first(self):
        ivs = parse_loci("chr03:200000-260000,chr07:5390000-5410000")
        hits = candidate_genes(ivs)
        ranked = prioritise(hits)
        # Named genes (Sub1A, GW7, OsWRKY45) should outrank generic Os symbols.
        assert ranked[0]["symbol"] in {"Sub1A", "GW7", "OsWRKY45"}


class TestReport:
    def test_report_content(self):
        ivs = parse_loci("chr01:1000000-1010000")
        hits = candidate_genes(ivs)
        md = generate_report(ivs, hits)
        assert "RicePilaf" in md
        assert "Candidate genes" in md
        assert "ClawBioCrop is a research" in md

    def test_report_empty(self):
        ivs = [{"chrom": "chr12", "start": 1, "end": 100}]
        md = generate_report(ivs, candidate_genes(ivs))
        assert "No candidate genes" in md


class TestOutputsAndCLI:
    def test_write_outputs(self, tmp_path):
        ivs = parse_loci("chr01:1000000-1010000")
        hits = candidate_genes(ivs)
        write_outputs(tmp_path, generate_report(ivs, hits), ivs, hits)
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "tables" / "candidate_genes.csv").exists()
        result = json.loads((tmp_path / "result.json").read_text())
        assert result["meta"]["n_candidates"] == len(hits)

    def test_demo_cli(self, tmp_path):
        rc = main(["--demo", "--output", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "report.md").exists()

    def test_bed_cli(self, tmp_path):
        rc = main(["--bed", str(EXAMPLES / "demo_peaks.bed"), "--output", str(tmp_path)])
        assert rc == 0
