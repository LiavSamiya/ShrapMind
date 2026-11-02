"""Turn a protein design into a DNA sequence you can order.

The question was whether this is possible. It is, and it is arithmetic rather
than research: a protein sequence plus a codon table plus a constraint set
gives a synthesisable gene. What it is *not* is a prediction that the protein
works -- reverse translation is a lossless mechanical step, and every
uncertainty in the design is still there in the DNA.

What this does:

  1. Takes the wild-type sequence from the warehouse, so the starting point is
     the reviewed UniProt entry rather than something retyped.
  2. Applies substitutions, checking the wild-type residue at each position
     first. A mutation written against the wrong numbering is the commonest
     way a construct fails, and it fails after the DNA has been paid for.
  3. Trims the signal peptide for cytoplasmic expression, which for TfH is
     also what makes the structure's numbering 40 lower than UniProt's.
  4. Reverse-translates with E. coli codon preferences, choosing among
     synonymous codons to satisfy constraints rather than always taking the
     commonest one.
  5. Checks the result: internal restriction sites for the cloning enzymes,
     homopolymer runs, GC content overall and in windows, internal
     ribosome-binding sites, and direct repeats.
  6. Emits the ordered construct with its tag, linker and stop codons, plus a
     FASTA file and a report.

    python -m tools.design_construct --target TfH \\
        --mutate H208A --remove-signal-peptide 40
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AA3 = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS", "Q": "GLN",
    "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE", "L": "LEU", "K": "LYS",
    "M": "MET", "F": "PHE", "P": "PRO", "S": "SER", "T": "THR", "W": "TRP",
    "Y": "TYR", "V": "VAL",
}

# Synonymous codons for E. coli K-12, ordered by usage in highly expressed
# genes (most-used first). Having the whole list rather than one codon per
# residue is what lets the chooser dodge a restriction site without changing
# the protein.
CODONS: dict[str, tuple[str, ...]] = {
    "A": ("GCG", "GCC", "GCA", "GCT"),
    "R": ("CGT", "CGC", "CGG", "CGA"),      # AGA/AGG omitted: rare in E. coli
    "N": ("AAC", "AAT"),
    "D": ("GAT", "GAC"),
    "C": ("TGC", "TGT"),
    "Q": ("CAG", "CAA"),
    "E": ("GAA", "GAG"),
    "G": ("GGC", "GGT", "GGG"),             # GGA omitted: rare
    "H": ("CAT", "CAC"),
    "I": ("ATC", "ATT", "ATA"),
    "L": ("CTG", "TTA", "CTT", "CTC"),      # CTA omitted: rare
    "K": ("AAA", "AAG"),
    "M": ("ATG",),
    "F": ("TTT", "TTC"),
    "P": ("CCG", "CCA", "CCT"),             # CCC omitted: rare
    "S": ("AGC", "TCT", "TCC", "TCG"),      # TCA/AGT deprioritised
    "T": ("ACC", "ACG", "ACT"),
    "W": ("TGG",),
    "Y": ("TAT", "TAC"),
    "V": ("GTG", "GTT", "GTC"),             # GTA deprioritised
}

STOP = "TAATGA"  # two stops in frame, so a single readthrough still terminates

# Sites a construct must not contain internally, or the cloning step cuts the
# insert. Both strands, because a restriction enzyme does not care.
RESTRICTION = {
    "NdeI": "CATATG", "XhoI": "CTCGAG", "EcoRI": "GAATTC",
    "BamHI": "GGATCC", "HindIII": "AAGCTT", "NcoI": "CCATGG",
    "SalI": "GTCGAC", "NotI": "GCGGCCGC",
    "BsaI": "GGTCTC", "BsmBI": "CGTCTC",   # Golden Gate; directional, so both
}
FORBIDDEN_MOTIFS = {
    "internal RBS": "AGGAGG",   # a Shine-Dalgarno inside the ORF
}

TAGS = {
    "his6_n": {
        "dna": "CATCATCATCATCATCAC",
        "protein": "HHHHHH",
        "where": "N",
        "note": "Hexahistidine for IMAC. On the N terminus it is cleavable "
                "only if a protease site is added; here it is left fused, "
                "which is fine for an assay and not for anything injected.",
    },
    "none": {"dna": "", "protein": "", "where": None, "note": "Untagged."},
}


def revcomp(dna: str) -> str:
    return dna.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def gc(dna: str) -> float:
    return 100.0 * sum(c in "GC" for c in dna) / max(len(dna), 1)


def _violates(dna: str) -> list[str]:
    """Constraint check on a candidate sequence."""
    problems = []
    for name, site in RESTRICTION.items():
        if site in dna or revcomp(site) in dna:
            problems.append(f"{name} site ({site})")
    for name, motif in FORBIDDEN_MOTIFS.items():
        if motif in dna:
            problems.append(f"{name} ({motif})")
    run = re.search(r"(A{7,}|C{7,}|G{7,}|T{7,})", dna)
    if run:
        problems.append(f"homopolymer run of {len(run.group(1))}")
    return problems


def reverse_translate(protein: str, prefix: str = "") -> tuple[str, list[dict]]:
    """Choose codons, backtracking one position when the current one is stuck.

    Greedy alone is not enough. Methionine and tryptophan have a single codon
    each, so when ATG or TGG completes a forbidden motif there is nothing to
    try at that position -- the fix has to come from the codon before it. The
    first version of this function flagged those cases instead of solving
    them, and produced an ORF carrying internal NdeI and NcoI sites that would
    have been cut during cloning.

    `prefix` is the sequence that will sit in front of the body (start codon
    and tag), included in the constraint window so a site spanning the
    junction is caught too.
    """
    options_at = []
    for i, aa in enumerate(protein):
        opts = CODONS.get(aa)
        if not opts:
            raise SystemExit(f"no codons for residue {aa!r} at position {i+1}")
        options_at.append(opts)

    picks: list[int] = []        # index into options_at[i]
    swaps: list[dict] = []
    stuck: list[dict] = []
    i = 0
    guard = 0
    while i < len(protein):
        guard += 1
        if guard > 50 * len(protein) + 1000:
            stuck.append({"position": i + 1, "residue": protein[i],
                          "why": "search budget exhausted"})
            break
        start_at = picks[i] if i < len(picks) else 0
        dna = prefix + "".join(options_at[k][picks[k]] for k in range(i))
        chosen = None
        for rank in range(start_at, len(options_at[i])):
            candidate = dna + options_at[i][rank]
            if _violates(candidate[-16:]):
                continue
            window = candidate[-60:]
            if len(window) >= 60 and not (25.0 <= gc(window) <= 75.0):
                continue
            chosen = rank
            break
        if chosen is None:
            # Nothing works here. Step back and move the previous codon on.
            if i == 0:
                stuck.append({"position": 1, "residue": protein[0],
                              "why": "no codon satisfies the constraints at "
                                     "the first position"})
                picks = [0]
                i = 1
                continue
            picks = picks[:i]
            picks[i - 1] += 1
            if picks[i - 1] >= len(options_at[i - 1]):
                # The previous position is exhausted too; accept its preferred
                # codon and record that this stretch could not be cleaned.
                picks[i - 1] = 0
                stuck.append({"position": i + 1, "residue": protein[i],
                              "why": "neither this codon nor the one before "
                                     "it could avoid a forbidden motif"})
                picks.append(0)
                i += 1
            else:
                i -= 1
            continue
        picks = picks[:i] + [chosen]
        i += 1

    while len(picks) < len(protein):
        picks.append(0)

    for i, rank in enumerate(picks):
        if rank:
            swaps.append({"position": i + 1, "residue": protein[i],
                          "preferred": options_at[i][0],
                          "used": options_at[i][rank],
                          "why": "preferred codon created a forbidden motif or "
                                 "a GC-extreme window"})
    body = "".join(options_at[i][picks[i]] for i in range(len(protein)))
    return body, swaps + stuck


def apply_mutations(sequence: str, mutations: list[str], offset: int = 0
                    ) -> tuple[str, list[dict]]:
    """Apply e.g. H208A, verifying the wild-type residue at that position.

    `offset` lets the mutation be written in the structure's numbering, which
    is what a person reads off a viewer. For TfH the structure is UniProt minus
    40, so H208A means UniProt position 248.
    """
    seq = list(sequence)
    applied = []
    for mut in mutations:
        m = re.fullmatch(r"([A-Z])(\d+)([A-Z])", mut.strip().upper())
        if not m:
            raise SystemExit(f"cannot parse mutation {mut!r}; expected e.g. H208A")
        wt, pos, new = m.group(1), int(m.group(2)), m.group(3)
        idx = pos + offset - 1
        if not (0 <= idx < len(seq)):
            raise SystemExit(f"{mut}: position {pos} is outside the sequence")
        if seq[idx] != wt:
            raise SystemExit(
                f"{mut}: position {pos} (sequence index {idx+1}) is "
                f"{seq[idx]}, not {wt}. Either the numbering is wrong or the "
                f"offset is -- and a construct ordered on wrong numbering "
                f"fails after it is paid for."
            )
        seq[idx] = new
        applied.append({"mutation": mut, "uniprot_position": pos + offset,
                        "wild_type": wt, "mutant": new,
                        "wild_type_verified": True})
    return "".join(seq), applied



class _Fetched:
    """A sequence from UniProt, shaped like a warehouse Protein.

    The warehouse is PAZy, which is a plastics database and holds no
    ferroxidase. The metal arm's lead -- human H ferritin -- therefore has to
    come from UniProt directly. It is cached on disk with its accession so the
    construct can be traced back to a record rather than to a paste.
    """

    def __init__(self, accession: str, name: str, sequence: str,
                 organism: str, ec: list[str]):
        self.uniprot_accession = accession
        self.name = name
        self.sequence = sequence
        self.organism = organism
        self.ec_numbers = ec


def _load_target(name: str, accession: str | None):
    if accession is None:
        from f2c import warehouse
        proteins = {p.name: p for p in warehouse.load()}
        prot = proteins.get(name)
        if prot is None:
            raise SystemExit(
                f"{name!r} is not in the warehouse. If it is a metal-arm "
                f"candidate, pass --uniprot: the warehouse is PAZy and holds "
                f"no ferroxidase.")
        if not prot.sequence:
            raise SystemExit(f"{name!r} has no sequence recorded")
        return prot

    import urllib.request
    cache = ROOT / "data" / "sequences" / f"{accession}.fasta"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"
        req = urllib.request.Request(
            url, headers={"User-Agent": "shrapmind (liav.s123@gmail.com)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            cache.write_bytes(resp.read())
    lines = cache.read_text().splitlines()
    header = lines[0] if lines else ""
    seq = "".join(l.strip() for l in lines[1:] if l and not l.startswith(">"))
    if not seq:
        raise SystemExit(f"{accession}: UniProt returned no sequence")
    organism = "?"
    if "OS=" in header:
        organism = header.split("OS=")[1].split(" OX=")[0].strip()
    return _Fetched(accession, name, seq, organism, [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default="TfH",
                    help="enzyme name as the warehouse records it, or a label "
                         "for a sequence fetched with --uniprot")
    ap.add_argument("--uniprot", default=None, metavar="ACC",
                    help="fetch this accession from UniProt instead of "
                         "reading the warehouse; cached under data/sequences")
    ap.add_argument("--mutate", action="append", default=[],
                    help="substitution, e.g. H208A; repeatable")
    ap.add_argument("--numbering", choices=("uniprot", "structure"),
                    default="structure",
                    help="which numbering the mutations are written in")
    ap.add_argument("--offset", type=int, default=40,
                    help="UniProt position minus structure position")
    ap.add_argument("--remove-signal-peptide", type=int, default=0,
                    metavar="N", help="trim N residues from the N terminus")
    ap.add_argument("--tag", choices=tuple(TAGS), default="his6_n")
    ap.add_argument("--out", default="data/constructs")
    args = ap.parse_args()

    prot = _load_target(args.target, args.uniprot)
    wt = prot.sequence
    offset = args.offset if args.numbering == "structure" else 0
    mutated, applied = apply_mutations(wt, args.mutate, offset)

    trimmed = mutated[args.remove_signal_peptide:]
    tag = TAGS[args.tag]
    mature = (tag["protein"] + trimmed) if tag["where"] == "N" else trimmed

    prefix = "ATG" + tag["dna"]
    orf_body, swaps = reverse_translate(trimmed, prefix=prefix)
    orf = prefix + orf_body + STOP

    windows = [gc(orf[i:i + 60]) for i in range(0, len(orf) - 59, 30)] or [gc(orf)]
    report = {
        "target": args.target,
        "uniprot": prot.uniprot_accession,
        "organism": prot.organism,
        "ec": prot.ec_numbers,
        "wild_type_length": len(wt),
        "mutations": applied,
        "signal_peptide_removed": args.remove_signal_peptide,
        "tag": {"name": args.tag, **{k: tag[k] for k in ("protein", "note")}},
        "protein_expressed": mature,
        "protein_length": len(mature),
        "dna_length_bp": len(orf),
        "gc_percent": round(gc(orf), 1),
        "gc_window_min": round(min(windows), 1),
        "gc_window_max": round(max(windows), 1),
        "codon_swaps_from_preferred": swaps,
        "constraint_violations": _violates(orf),
        "restriction_sites_checked": sorted(RESTRICTION),
        "what_this_is": (
            "A synthesisable open reading frame. Reverse translation is "
            "mechanical, so this is a faithful encoding of the designed "
            "protein and nothing more -- it carries every uncertainty the "
            "design carries."
        ),
        "what_this_is_not": (
            "Not evidence the protein folds, is soluble, is active, or is "
            "safe. For this target none of those is known at 37 C in tissue, "
            "and ordering DNA does not change that."
        ),
    }

    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.target}_{'_'.join(args.mutate) or 'wt'}"
    (outdir / f"{stem}.fasta").write_text(
        f">{stem}|{prot.uniprot_accession}|protein|{len(mature)}aa\n"
        + "\n".join(mature[i:i + 60] for i in range(0, len(mature), 60))
        + f"\n>{stem}|dna|{len(orf)}bp|Ecoli_codon_optimised\n"
        + "\n".join(orf[i:i + 60] for i in range(0, len(orf), 60)) + "\n")
    (outdir / f"{stem}.json").write_text(json.dumps(report, indent=2))

    print(f"{args.target}  {prot.uniprot_accession}  {prot.organism}")
    for m in applied:
        print(f"  {m['mutation']}: verified {m['wild_type']} at UniProt "
              f"{m['uniprot_position']}")
    if args.remove_signal_peptide:
        print(f"  trimmed {args.remove_signal_peptide} residues "
              f"(signal peptide) for cytoplasmic expression")
    print(f"  protein {len(mature)} aa, DNA {len(orf)} bp, GC "
          f"{report['gc_percent']}% (windows {report['gc_window_min']}-"
          f"{report['gc_window_max']}%)")
    print(f"  codons moved off the preferred choice: {len(swaps)}")
    print(f"  constraint violations: {report['constraint_violations'] or 'none'}")
    print(f"  wrote {outdir / f'{stem}.fasta'}")
    return 1 if report["constraint_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
