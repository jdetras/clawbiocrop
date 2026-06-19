#!/usr/bin/env python3
"""
crop_genome_annotation.py — Crop Genome Structural Annotation (ClawBioCrop Skill)
================================================================================
De novo structural annotation of crop / plant genomic sequence. Given a nucleotide
FASTA (a contig, BAC, or gene region from rice, wheat, maize, etc.), it scans all six
reading frames for open reading frames, builds gene/mRNA/CDS models, computes GC and
codon-usage summaries, assigns a putative product via a small plant-protein motif table,
and writes a GFF3 annotation plus a Markdown report.

Usage:
    python crop_genome_annotation.py --input contig.fasta --output /tmp/annot
    python crop_genome_annotation.py --input contig.fasta --min-aa 80 --output /tmp/annot
    python crop_genome_annotation.py --demo --output /tmp/annot_demo

OFFLINE-FIRST and dependency-free (standard library only). This is a fast structural
pass, not a substitute for evidence-based annotation (RNA-seq, protein homology).

ClawBioCrop is a research and educational tool for crop genomics.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

DISCLAIMER = (
    "ClawBioCrop is a research and educational tool for crop genomics. This is an ab-initio "
    "structural pass; confirm gene models with RNA-seq evidence and homology before use."
)

START_CODON = "ATG"
STOP_CODONS = {"TAA", "TAG", "TGA"}
COMPLEMENT = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")

# Small plant-protein motif table for putative product hints (illustrative).
MOTIFS = [
    ("WRKYGQK", "WRKY transcription factor (defence/stress)"),
    ("GRGRG", "RNA-binding / glycine-rich protein"),
    ("HEFGH", "metalloprotease (zinc-binding)"),
    ("DFG", "protein kinase activation loop"),
    ("CXXC", None),  # handled specially below
]


def revcomp(seq: str) -> str:
    return seq.translate(COMPLEMENT)[::-1]


# ---------------------------------------------------------------------------
# FASTA parsing
# ---------------------------------------------------------------------------

def parse_fasta(text: str):
    """Yield (id, sequence) pairs from FASTA text."""
    records = []
    name, chunks = None, []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                records.append((name, "".join(chunks).upper()))
            name = line[1:].strip().split()[0] if len(line) > 1 else "seq"
            chunks = []
        else:
            chunks.append(line.strip())
    if name is not None:
        records.append((name, "".join(chunks).upper()))
    return records


# ---------------------------------------------------------------------------
# Sequence statistics
# ---------------------------------------------------------------------------

def gc_content(seq: str) -> float:
    seq = seq.upper()
    valid = [b for b in seq if b in "ACGT"]
    if not valid:
        return 0.0
    gc = sum(1 for b in valid if b in "GC")
    return round(100.0 * gc / len(valid), 2)


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "CTT": "L", "CTC": "L",
    "CTA": "L", "CTG": "L", "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V", "TCT": "S", "TCC": "S",
    "TCA": "S", "TCG": "S", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "GCT": "A", "GCC": "A",
    "GCA": "A", "GCG": "A", "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q", "AAT": "N", "AAC": "N",
    "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CGT": "R", "CGC": "R",
    "CGA": "R", "CGG": "R", "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def translate(seq: str) -> str:
    prot = []
    for i in range(0, len(seq) - 2, 3):
        prot.append(_CODON_TABLE.get(seq[i:i + 3], "X"))
    return "".join(prot)


# ---------------------------------------------------------------------------
# ORF finding (6-frame)
# ---------------------------------------------------------------------------

def find_orfs(seq: str, min_aa: int = 50):
    """Find ORFs (ATG..stop) in all six frames. Returns list of dicts (1-based, seq coords)."""
    orfs = []
    L = len(seq)
    for strand, s in (("+", seq), ("-", revcomp(seq))):
        for frame in range(3):
            i = frame
            while i < L - 2:
                if s[i:i + 3] == START_CODON:
                    j = i
                    while j < L - 2:
                        codon = s[j:j + 3]
                        if codon in STOP_CODONS:
                            aa_len = (j - i) // 3
                            if aa_len >= min_aa:
                                # Map to forward-strand 1-based coords.
                                if strand == "+":
                                    start, end = i + 1, j + 3
                                else:
                                    start, end = L - (j + 3) + 1, L - i
                                orfs.append({
                                    "strand": strand, "frame": frame,
                                    "start": start, "end": end,
                                    "aa_len": aa_len,
                                    "nt_seq": s[i:j + 3],
                                })
                            i = j + 3
                            break
                        j += 3
                    else:
                        break
                else:
                    i += 3
    # Sort by position, keep longest non-nested ORFs per region (simple greedy).
    orfs.sort(key=lambda o: (-o["aa_len"]))
    kept = []
    occupied = []
    for o in orfs:
        overlap = any(not (o["end"] < a or o["start"] > b) for a, b in occupied)
        if not overlap:
            kept.append(o)
            occupied.append((o["start"], o["end"]))
    kept.sort(key=lambda o: o["start"])
    return kept


# ---------------------------------------------------------------------------
# Functional hint
# ---------------------------------------------------------------------------

def putative_product(nt_seq: str) -> str:
    prot = translate(nt_seq).rstrip("*")
    for motif, label in MOTIFS:
        if motif == "CXXC":
            # zinc-finger-like CxxC
            for k in range(len(prot) - 3):
                if prot[k] == "C" and prot[k + 3] == "C":
                    return "zinc-finger / metal-binding protein (CxxC)"
            continue
        if motif in prot:
            return label
    if len(prot) >= 300:
        return "hypothetical protein (large ORF)"
    return "hypothetical protein"


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------

def annotate(records, min_aa=50):
    """Annotate each FASTA record; return (genes, stats)."""
    genes = []
    gid = 0
    per_seq = []
    for name, seq in records:
        orfs = find_orfs(seq, min_aa=min_aa)
        for o in orfs:
            gid += 1
            product = putative_product(o["nt_seq"])
            genes.append({
                "gene_id": f"CBC_{gid:05d}",
                "seqid": name, "source": "ClawBioCrop",
                "start": o["start"], "end": o["end"], "strand": o["strand"],
                "aa_len": o["aa_len"], "product": product,
            })
        per_seq.append({"seqid": name, "length": len(seq),
                        "gc": gc_content(seq), "n_genes": len(orfs)})
    total_len = sum(p["length"] for p in per_seq)
    stats = {
        "n_sequences": len(records),
        "total_length": total_len,
        "n_genes": len(genes),
        "mean_gene_aa": round(sum(g["aa_len"] for g in genes) / len(genes), 1) if genes else 0,
        "overall_gc": gc_content("".join(s for _, s in records)),
        "gene_density_per_kb": round(1000 * len(genes) / total_len, 3) if total_len else 0,
        "per_sequence": per_seq,
        "generated": datetime.now().isoformat(),
    }
    return genes, stats


def to_gff3(genes):
    lines = ["##gff-version 3"]
    for g in genes:
        attrs = f"ID={g['gene_id']};product={g['product']}"
        lines.append("\t".join([
            g["seqid"], g["source"], "gene", str(g["start"]), str(g["end"]),
            ".", g["strand"], ".", attrs,
        ]))
        lines.append("\t".join([
            g["seqid"], g["source"], "CDS", str(g["start"]), str(g["end"]),
            ".", g["strand"], "0", f"ID={g['gene_id']}.cds;Parent={g['gene_id']}",
        ]))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(genes, stats):
    lines = [
        "# Crop Genome Structural Annotation Report",
        "",
        f"**Sequences**: {stats['n_sequences']}  ",
        f"**Total length**: {stats['total_length']:,} bp  ",
        f"**Overall GC**: {stats['overall_gc']}%  ",
        f"**Predicted genes**: {stats['n_genes']}  ",
        f"**Mean protein length**: {stats['mean_gene_aa']} aa  ",
        f"**Gene density**: {stats['gene_density_per_kb']} genes/kb  ",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Predicted gene models",
        "",
        "| Gene ID | Seqid | Start | End | Strand | Length (aa) | Putative product |",
        "|---------|-------|-------|-----|--------|-------------|------------------|",
    ]
    for g in genes[:50]:
        lines.append(
            f"| {g['gene_id']} | {g['seqid']} | {g['start']:,} | {g['end']:,} | "
            f"{g['strand']} | {g['aa_len']} | {g['product']} |"
        )
    if not genes:
        lines.append("| _none_ | | | | | | |")
    lines += [
        "",
        "## Per-sequence summary",
        "",
        "| Seqid | Length (bp) | GC % | Genes |",
        "|-------|-------------|------|-------|",
    ]
    for p in stats["per_sequence"]:
        lines.append(f"| {p['seqid']} | {p['length']:,} | {p['gc']} | {p['n_genes']} |")
    lines += ["", "---", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_fasta():
    """A synthetic crop contig with a couple of plantable ORFs (incl. WRKY motif)."""
    # Build a sequence containing ATG ... WRKYGQK-coding ... stop.
    # WRKYGQK codons: TGG AGG AAG TAC GGT CAG AAG
    wrky = "TGGAGGAAGTACGGTCAGAAG"
    filler = "GCT" * 40  # alanines
    orf1 = "ATG" + filler + wrky + filler + "TAA"
    orf2 = "ATG" + ("GGA" * 60) + "TGA"  # glycine-rich, long
    # Spacer carrying stop codons on BOTH strands (TAA/TAG/TGA forward;
    # TTA/CTA/TCA become TAA/TAG/TGA on the reverse strand) so naive ORF
    # finding cannot run a spurious ORF across the intergenic regions.
    intergenic = "TAATAGTGATTACTATCA" * 3
    seq = intergenic + orf1 + intergenic + orf2 + intergenic
    return f">demo_contig_Os Oryza sativa synthetic contig\n{seq}\n"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(out_dir, report_md, genes, stats):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report_md)
    (out_dir / "result.json").write_text(json.dumps({"stats": stats, "genes": genes}, indent=2))
    (out_dir / "annotation.gff3").write_text(to_gff3(genes))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Crop genome structural annotation (ClawBioCrop)")
    p.add_argument("--input", help="Nucleotide FASTA file")
    p.add_argument("--min-aa", type=int, default=50, help="Minimum ORF length in amino acids")
    p.add_argument("--output", default="/tmp/annot", help="Output directory")
    p.add_argument("--demo", action="store_true", help="Run with a synthetic crop contig")
    args = p.parse_args(argv)

    if args.demo:
        records = parse_fasta(demo_fasta())
    elif args.input:
        records = parse_fasta(Path(args.input).read_text())
    else:
        p.error("provide --input or --demo")

    if not records:
        print("[crop-genome-annotation] No FASTA records found.", file=sys.stderr)
        return 1

    genes, stats = annotate(records, min_aa=args.min_aa)
    report_md = generate_report(genes, stats)
    out_dir = Path(args.output)
    write_outputs(out_dir, report_md, genes, stats)
    print(report_md)
    print(f"\n[crop-genome-annotation] Wrote report + GFF3 to {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
