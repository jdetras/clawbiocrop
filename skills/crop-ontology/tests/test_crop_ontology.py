"""Tests for crop-ontology — Crop/Plant/Trait ontology lookup."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crop_ontology import (
    TERMS,
    ONTOLOGIES,
    search_terms,
    get_term,
    generate_report,
    write_outputs,
    main,
)


class TestTermSet:
    def test_non_empty(self):
        assert len(TERMS) >= 5

    def test_required_keys(self):
        for t in TERMS:
            for k in ("id", "name", "ontology", "definition", "parents", "synonyms"):
                assert k in t

    def test_ontologies_known(self):
        for t in TERMS:
            assert t["ontology"] in ONTOLOGIES


class TestSearch:
    def test_search_grain_yield(self):
        results = search_terms("grain yield")
        assert any(t["id"] == "TO:0000396" for t in results)

    def test_search_synonym(self):
        results = search_terms("panicle")
        ids = {t["id"] for t in results}
        assert "PO:0009049" in ids  # inflorescence has 'panicle' synonym

    def test_search_ranked_exact_first(self):
        results = search_terms("drought tolerance")
        assert results[0]["id"] == "TO:0000174"

    def test_search_ontology_filter(self):
        results = search_terms("seed", ontology="PO")
        assert all(t["ontology"] == "PO" for t in results)

    def test_search_no_match(self):
        assert search_terms("xyzzy-not-a-trait") == []

    def test_search_case_insensitive(self):
        assert search_terms("DROUGHT") == search_terms("drought")


class TestLookup:
    def test_get_term(self):
        t = get_term("TO:0000598")
        assert t is not None
        assert "submergence" in t["name"]

    def test_get_term_missing(self):
        assert get_term("TO:9999999") is None


class TestReport:
    def test_report_content(self):
        results = search_terms("grain yield")
        md = generate_report("grain yield", results)
        assert "Crop & Plant Ontology" in md
        assert "TO:0000396" in md
        assert "ClawBioCrop is a research" in md

    def test_report_empty(self):
        md = generate_report("xyzzy", [])
        assert "No ontology terms matched" in md


class TestOutputsAndCLI:
    def test_write_outputs(self, tmp_path):
        results = search_terms("grain yield")
        write_outputs(tmp_path, generate_report("grain yield", results), results,
                      {"n_matches": len(results)})
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "result.json").exists()
        assert (tmp_path / "tables" / "terms.csv").exists()
        data = json.loads((tmp_path / "result.json").read_text())
        assert data["meta"]["n_matches"] == len(results)

    def test_demo_cli(self, tmp_path):
        rc = main(["--demo", "--output", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "report.md").exists()

    def test_term_cli(self, tmp_path):
        rc = main(["--term", "TO:0000174", "--output", str(tmp_path)])
        assert rc == 0
        assert "TO:0000174" in (tmp_path / "report.md").read_text()
