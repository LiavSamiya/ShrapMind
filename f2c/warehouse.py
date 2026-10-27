"""Build and load the local catalyst warehouse.

The store is measurement-level on purpose: one row per observation, never a
single averaged activity per enzyme. Collapsing assays run at different pH and
temperature would erase exactly the signal the ranker needs.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .schema import Evidence, Observation, Protein
from .sources import brenda, pazy, uniprot

DEFAULT_STORE = Path(__file__).resolve().parent.parent / "data" / "warehouse.json"


def _dump(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {k: _dump(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dump(v) for v in obj]
    return obj


def save(proteins: list[Protein], path: Path = DEFAULT_STORE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "proteins": [_dump(p) for p in proteins],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _load_protein(rec: dict[str, Any]) -> Protein:
    observations = [
        Observation(
            metric=o["metric"],
            value=o["value"],
            unit=o["unit"],
            evidence=Evidence(**o["evidence"]),
            conditions=o.get("conditions") or {},
            note=o.get("note"),
        )
        for o in rec.pop("observations", [])
    ]
    evidence = [Evidence(**e) for e in rec.pop("evidence", [])]
    return Protein(evidence=evidence, observations=observations, **rec)


def load(path: Path = DEFAULT_STORE) -> list[Protein]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No warehouse at {path}. Run `python -m f2c.cli build` first."
        )
    payload = json.loads(path.read_text())
    return [_load_protein(rec) for rec in payload["proteins"]]


def enrich_from_brenda(proteins: list[Protein], subset_path: Path) -> dict[str, int]:
    """Attach BRENDA's measured constants, skipping references that cannot be right.

    A reference whose PMID fails the plausibility check is dropped rather than
    carried: a measurement is only as citable as the paper behind it.
    """
    if not subset_path.exists():
        return {"added": 0, "proteins_touched": 0, "suspect_references": 0}

    subset = brenda.load_subset(subset_path)
    release = subset.get("release")
    bad_pmids = brenda.load_bad_pmids(subset_path.parent / "bad_references.json")
    by_accession: dict[str, list[Protein]] = {}
    for protein in proteins:
        if protein.uniprot_accession:
            by_accession.setdefault(protein.uniprot_accession, []).append(protein)

    added = 0
    touched: set[str] = set()
    suspect_total = 0

    for entry in subset["data"].values():
        suspects = brenda.suspect_references(entry)
        suspect_total += len(suspects)
        skip = {s["reference_id"] for s in suspects}

        for accession, targets in by_accession.items():
            observations = list(
                brenda.observations_for_accession(
                    entry,
                    accession,
                    release=release,
                    skip_reference_ids=skip,
                    bad_pmids=bad_pmids,
                )
            )
            if not observations:
                continue
            for protein in targets:
                protein.observations.extend(observations)
                protein.evidence.append(
                    Evidence(
                        source_db=brenda.SOURCE_DB,
                        retrieved_at=_dt.date.today().isoformat(),
                        level="experimental",
                        source_version=release,
                    )
                )
                touched.add(protein.protein_id)
                added += len(observations)

    return {
        "added": added,
        "proteins_touched": len(touched),
        "suspect_references": suspect_total,
    }


def build(
    store: Path = DEFAULT_STORE,
    raw_dir: Path | None = None,
    refresh: bool = False,
    uniprot_limit: int | None = None,
) -> list[Protein]:
    """Pull PAZy, enrich from UniProt and BRENDA, and persist the result."""
    raw_dir = raw_dir or store.parent / "raw"
    raw_path = raw_dir / "pazy_proteins.json"

    if refresh or not raw_path.exists():
        pazy.fetch(raw_path)

    proteins = pazy.load(raw_path)
    uniprot.enrich_all(
        proteins, cache_dir=raw_dir / "uniprot", limit=uniprot_limit
    )
    enrich_from_brenda(proteins, raw_dir / "brenda" / "subset.json")
    save(proteins, store)
    return proteins


def stats(proteins: list[Protein]) -> dict[str, Any]:
    with_temp = sum(
        1 for p in proteins if any(o.value is not None for o in p.observations_for("temperature_optimum_c"))
    )
    with_ph = sum(
        1 for p in proteins if any(o.value is not None for o in p.observations_for("ph_optimum"))
    )
    substrates: dict[str, int] = {}
    for p in proteins:
        for sub in p.substrates:
            key = sub.get("abbreviation") or sub.get("name") or "?"
            substrates[key] = substrates.get(key, 0) + 1
    return {
        "proteins": len(proteins),
        "with_uniprot": sum(1 for p in proteins if p.uniprot_accession),
        "reviewed": sum(1 for p in proteins if p.reviewed),
        "with_structure": sum(1 for p in proteins if p.pdb_ids),
        "with_temperature_optimum": with_temp,
        "with_ph_optimum": with_ph,
        "by_substrate": dict(sorted(substrates.items(), key=lambda kv: -kv[1])),
    }
