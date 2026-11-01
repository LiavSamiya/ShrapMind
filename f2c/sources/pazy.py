"""PAZy ingest -- the experimental seed set.

PAZy curates enzymes whose activity on a given plastic was demonstrated in the
lab, with the paper attached. That makes it the one source here that yields
gold labels rather than features, which is why the warehouse is seeded from it.
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.request
from pathlib import Path
from typing import Any

from ..schema import Evidence, Protein

PAZY_BULK_URL = "https://api.pazy.eu/api/proteins/json/"
SOURCE_DB = "PAZy"


def fetch(dest: Path, timeout: int = 180) -> Path:
    """Download the full PAZy protein export to `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(PAZY_BULK_URL, timeout=timeout) as resp:
        payload = resp.read()
    dest.write_bytes(payload)
    return dest


def _records(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return raw.get("results", [])
    return list(raw)


def load(path: Path, retrieved_at: str | None = None) -> list[Protein]:
    """Parse a PAZy export into Protein entities."""
    retrieved_at = retrieved_at or _dt.date.today().isoformat()
    raw = json.loads(Path(path).read_text())

    proteins: list[Protein] = []
    for rec in _records(raw):
        # PAZy only publishes entries whose activity was shown experimentally;
        # anything else would be a candidate, not a label.
        if not rec.get("verified"):
            continue

        literature = rec.get("literature") or []
        evidence = [
            Evidence(
                source_db=SOURCE_DB,
                retrieved_at=retrieved_at,
                level="experimental",
                doi=lit.get("doi"),
            )
            for lit in literature
        ] or [
            Evidence(
                source_db=SOURCE_DB,
                retrieved_at=retrieved_at,
                level="experimental",
            )
        ]

        organism = rec.get("organism") or {}
        pdb_ids = [
            acc["accession"]
            for acc in (rec.get("accessions") or [])
            if acc.get("database") == "PDB" and acc.get("accession")
        ]

        proteins.append(
            Protein(
                protein_id=f"pazy:{rec['id']}",
                name=rec.get("name") or f"PAZy protein {rec['id']}",
                sequence=rec.get("amino_acid_sequence") or "",
                sequence_md5=rec.get("sequence_md5") or "",
                organism=organism.get("scientific_name") or "unknown",
                taxon_id=organism.get("ncbi_taxonomy_id"),
                substrates=rec.get("substrates") or [],
                uniprot_accession=rec.get("uniprot_accession") or None,
                evidence=evidence,
                literature=literature,
                pdb_ids=sorted(set(pdb_ids)),
                alphafold_url=rec.get("alphafold_url"),
            )
        )
    return proteins


def substrate_abbreviations(proteins: list[Protein]) -> set[str]:
    return {
        sub.get("abbreviation")
        for p in proteins
        for sub in p.substrates
        if sub.get("abbreviation")
    }
