"""UniProtKB enrichment.

Adds the canonical reaction keys (EC, Rhea, ChEBI) and, where Swiss-Prot has
curated them, the measured optima and kinetic constants. Every value carries
the PubMed id UniProt attributes it to, so nothing here can become an
unsourced number downstream.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from ..schema import Evidence, Observation, Protein

ENTRY_URL = "https://rest.uniprot.org/uniprotkb/{accession}.json"
SOURCE_DB = "UniProtKB"

# "Optimum temperature is 40 degrees Celsius", "Optimum pH is 9", "pH 8.5-9.5".
_TEMP_RE = re.compile(r"optimum temperature is\s*(?:around\s*)?(\d+(?:\.\d+)?)", re.I)
_PH_RE = re.compile(r"optimum ph is\s*(?:around\s*)?(\d+(?:\.\d+)?)", re.I)


def _pmids(evidences: Iterable[dict[str, Any]] | None) -> list[str]:
    return [
        str(e["id"])
        for e in (evidences or [])
        if e.get("source") == "PubMed" and e.get("id")
    ]


def fetch_entry(accession: str, cache_dir: Path, timeout: int = 30) -> dict[str, Any] | None:
    """Fetch one UniProt entry, caching it so re-runs do not re-download."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{accession}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    try:
        with urllib.request.urlopen(
            ENTRY_URL.format(accession=accession), timeout=timeout
        ) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None

    # An obsolete or merged accession comes back without an entryType.
    if not payload.get("entryType"):
        return None
    cached.write_text(json.dumps(payload))
    return payload


def _text_observation(
    comment: dict[str, Any],
    key: str,
    metric: str,
    pattern: re.Pattern[str],
    unit: str,
    retrieved_at: str,
) -> list[Observation]:
    """Pull an optimum out of UniProt's free-text dependence comments.

    The parsed number and the sentence it came from are both kept: the number
    is what the ranker compares, the sentence is what a reviewer checks.
    """
    out: list[Observation] = []
    for text in (comment.get(key) or {}).get("texts", []) or []:
        value_text = text.get("value") or ""
        match = pattern.search(value_text)
        pmids = _pmids(text.get("evidences"))
        out.append(
            Observation(
                metric=metric,
                value=float(match.group(1)) if match else None,
                unit=unit if match else None,
                evidence=Evidence(
                    source_db=SOURCE_DB,
                    retrieved_at=retrieved_at,
                    level="experimental" if pmids else "curated",
                    pmid=pmids[0] if pmids else None,
                ),
                conditions={"all_pmids": pmids} if len(pmids) > 1 else {},
                note=value_text,
            )
        )
    return out


def enrich(
    protein: Protein, cache_dir: Path, retrieved_at: str | None = None
) -> Protein:
    """Attach UniProt annotation to a protein in place and return it."""
    retrieved_at = retrieved_at or _dt.date.today().isoformat()
    if not protein.uniprot_accession:
        return protein

    entry = fetch_entry(protein.uniprot_accession, cache_dir)
    if entry is None:
        return protein

    protein.reviewed = "reviewed" in (entry.get("entryType") or "").lower()

    desc = entry.get("proteinDescription") or {}
    rec_name = desc.get("recommendedName") or {}
    protein.ec_numbers = sorted(
        {ec["value"] for ec in (rec_name.get("ecNumbers") or []) if ec.get("value")}
    )

    rhea: set[str] = set()
    chebi: set[str] = set()
    reactions: list[str] = []

    for comment in entry.get("comments", []) or []:
        ctype = comment.get("commentType")

        if ctype == "CATALYTIC ACTIVITY":
            reaction = comment.get("reaction") or {}
            if reaction.get("name"):
                reactions.append(reaction["name"])
            for xref in reaction.get("reactionCrossReferences", []) or []:
                if xref.get("database") == "Rhea":
                    rhea.add(xref["id"])
                elif xref.get("database") == "ChEBI":
                    chebi.add(xref["id"])

        elif ctype == "BIOPHYSICOCHEMICAL PROPERTIES":
            protein.observations.extend(
                _text_observation(
                    comment, "temperatureDependence", "temperature_optimum_c",
                    _TEMP_RE, "C", retrieved_at,
                )
            )
            protein.observations.extend(
                _text_observation(
                    comment, "phDependence", "ph_optimum", _PH_RE, "pH", retrieved_at
                )
            )
            kinetics = comment.get("kineticParameters") or {}
            for km in kinetics.get("michaelisConstants", []) or []:
                pmids = _pmids(km.get("evidences"))
                protein.observations.append(
                    Observation(
                        metric="km",
                        value=km.get("constant"),
                        unit=km.get("unit"),
                        evidence=Evidence(
                            source_db=SOURCE_DB,
                            retrieved_at=retrieved_at,
                            level="experimental" if pmids else "curated",
                            pmid=pmids[0] if pmids else None,
                        ),
                        conditions={"substrate": km.get("substrate")},
                    )
                )

    protein.rhea_ids = sorted(rhea)
    protein.chebi_ids = sorted(chebi)
    protein.catalytic_reactions = reactions

    if not protein.pdb_ids:
        protein.pdb_ids = sorted(
            {
                x["id"]
                for x in entry.get("uniProtKBCrossReferences", []) or []
                if x.get("database") == "PDB" and x.get("id")
            }
        )

    protein.evidence.append(
        Evidence(
            source_db=SOURCE_DB,
            retrieved_at=retrieved_at,
            level="curated" if protein.reviewed else "predicted",
            source_version=entry.get("entryAudit", {}).get("entryVersion"),
        )
    )
    return protein


def enrich_all(
    proteins: list[Protein],
    cache_dir: Path,
    pause: float = 0.12,
    limit: int | None = None,
) -> list[Protein]:
    targets = [p for p in proteins if p.uniprot_accession]
    if limit is not None:
        targets = targets[:limit]
    for i, protein in enumerate(targets):
        enrich(protein, cache_dir)
        # Be a good citizen against a public API.
        if pause and i < len(targets) - 1:
            time.sleep(pause)
    return proteins
