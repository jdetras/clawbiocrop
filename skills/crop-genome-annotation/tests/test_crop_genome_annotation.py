"""Tests for crop-genome-annotation — ab-initio crop gene structure annotation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crop_genome_annotation import (
    parse_fasta,
    gc_content,
    revcomp,
    translate,
    find_orfs,
    putative_product,
    annotate,
    to_gff3,
    generate_report,
    demo_fasta,
    write_outputs,
    main,
)


class TestSequenceUtils:
    def test_revcomp(self):
        assert revcomp("ATGC") == "GCAT"

    def test_gc_content(self):
        assert gc_content("GGCC") == 100.0
        assert gc_content("ATAT") == 0.0

    def test_translate(self):
        assert translate("ATGGGATAA") == "MG*"

    def test_parse_fasta(self):
        recs = parse_fasta(">s1 desc\nATGC\nGGGG\n>s2\nTTTT\n")
        assert recs == [("s1", "ATGCGGGG"), ("s2", "TTTT")]


class TestORFs:
    def test_finds_forward_orf(self):
        seq = "AAA" + "ATG" + ("GCT" * 60) + "TAA" + "AAA"
        orfs = find_orfs(seq, min_aa=50)
        assert len(orfs) >= 1
        assert orfs[0]["strand"] == "+"
        assert orfs[0]["aa_len"] >= 50

    def test_min_aa_filter(self):
        seq = "ATG" + ("GCT" * 10) + "TAA"
        assert find_orfs(seq, min_aa=50) == []

    def test_reverse_strand(self):
        fwd = "ATG" + ("GCT" * 60) + "TAA"
        seq = revcomp(fwd)
        orfs = find_orfs(seq, min_aa=50)
        assert any(o["strand"] == "-" for o in orfs)


class TestFunctionalHint:
    def test_wrky_motif(self):
        # Encode WRKYGQK
        wrky_nt = "TGGAGGAAGTACGGTCAGAAG"
        nt = "ATG" + wrky_nt + "TAA"
        assert "WRKY" in putative_product(nt)

    def test_default_hypothetical(self):
        nt = "ATG" + ("GCT" * 5) + "TAA"
        assert "hypothetical" in putative_product(nt)


class TestAnnotate:
    def test_demo_produces_genes(self):
        records = parse_fasta(demo_fasta())
        genes, stats = annotate(records, min_aa=50)
        assert stats["n_genes"] >= 1
        assert stats["overall_gc"] > 0
        assert any("WRKY" in g["product"] for g in genes)

    def test_gff3_structure(self):
        records = parse_fasta(demo_fasta())
        genes, _ = annotate(records, min_aa=50)
        gff = to_gff3(genes)
        assert gff.startswith("##gff-version 3")
        assert "\tgene\t" in gff
        assert "\tCDS\t" in gff

    def test_gene_ids_unique(self):
        records = parse_fasta(demo_fasta())
        genes, _ = annotate(records, min_aa=50)
        ids = [g["gene_id"] for g in genes]
        assert len(ids) == len(set(ids))


class TestReportAndCLI:
    def test_report_content(self):
        records = parse_fasta(demo_fasta())
        genes, stats = annotate(records, min_aa=50)
        md = generate_report(genes, stats)
        assert "Crop Genome Structural Annotation" in md
        assert "Predicted gene models" in md
        assert "ClawBioCrop is a research" in md

    def test_write_outputs(self, tmp_path):
        records = parse_fasta(demo_fasta())
        genes, stats = annotate(records, min_aa=50)
        write_outputs(tmp_path, generate_report(genes, stats), genes, stats)
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "annotation.gff3").exists()
        data = json.loads((tmp_path / "result.json").read_text())
        assert data["stats"]["n_genes"] == len(genes)

    def test_demo_cli(self, tmp_path):
        rc = main(["--demo", "--output", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "annotation.gff3").exists()

    def test_input_cli(self, tmp_path):
        fasta = tmp_path / "in.fasta"
        fasta.write_text(demo_fasta())
        rc = main(["--input", str(fasta), "--output", str(tmp_path / "out")])
        assert rc == 0
        assert (tmp_path / "out" / "report.md").exists()
