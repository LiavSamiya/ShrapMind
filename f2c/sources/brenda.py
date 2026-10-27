"""BRENDA ingest -- measured constants with their assay conditions.

BRENDA is what turns the ranking from "how well evidenced is this enzyme" into
"how well does it work at 37 C and pH 7.4", because every value here arrives
with the conditions it was measured under in a free-text comment.

Two cautions are built in rather than assumed away:

* a value is kept tied to its own conditions and never merged with another;
* a reference's PMID is treated as a claim to be checked, not a fact. BRENDA
  is curated and still carries wrong ids -- in release 2026.1, EC 3.1.1.101
  attributes a 2018 PET-degradation paper to PMID 2937183, which is a 1986
  Russian paper on paediatric oral surgery. `suspect_references` finds these.

Licence: BRENDA is CC BY 4.0; cite Chang et al., Nucleic Acids Research.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Iterator

from ..schema import Evidence, Observation

SOURCE_DB = "BRENDA"

# BRENDA writes measured values as "3.2 {4-nitrophenyl octanoate}".
_VALUE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:\{(.*)\})?\s*$")
# Conditions live in the comment: "pH 8.0, 40°C", "pH 7.4, 30 °C".
_PH_RE = re.compile(r"pH\s*(\d+(?:\.\d+)?)", re.I)
_TEMP_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*C\b")

# BRENDA field -> the metric name used in the warehouse.
METRICS = {
    "temperature_optimum": "temperature_optimum_c",
    "ph_optimum": "ph_optimum",
    "turnover_number": "kcat",
    "km_value": "km",
    "kcat_km_value": "kcat_km",
    "specific_activity": "specific_activity",
}
UNITS = {
    "temperature_optimum_c": "C",
    "ph_optimum": "pH",
    "kcat": "1/s",
    "km": "mM",
    "kcat_km": "1/(mM*s)",
    "specific_activity": "umol/min/mg",
}


def load_subset(path: Path) -> dict[str, Any]:
    """Load a pre-extracted BRENDA subset: {"release": ..., "data": {ec: {...}}}."""
    return json.loads(Path(path).read_text())


def extract_subset(full_json: Path, ec_numbers: set[str], dest: Path) -> dict[str, Any]:
    """Pull only the EC entries we need out of the full 700 MB release."""
    payload = json.loads(Path(full_json).read_text())
    wanted = {ec for ec in ec_numbers if "-" not in ec}
    subset = {
        "release": payload.get("release"),
        "data": {k: v for k, v in payload["data"].items() if k in wanted},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(subset))
    return subset


def _parse_value(raw: Any) -> tuple[float | None, str | None]:
    match = _VALUE_RE.match(str(raw))
    if not match:
        return None, None
    substrate = (match.group(2) or "").strip() or None
    return float(match.group(1)), substrate


def _conditions(comment: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not comment:
        return out
    ph = _PH_RE.search(comment)
    temp = _TEMP_RE.search(comment)
    if ph:
        out["assay_ph"] = float(ph.group(1))
    if temp:
        out["assay_temperature_c"] = float(temp.group(1))
    out["comment"] = comment
    return out


def suspect_references(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """References whose PMID cannot be right on its face.

    A PMID is assigned in rough publication order, so an id far too small for
    the stated year is a mismatch. This is a cheap pre-filter; the real check
    is resolving the id and comparing titles.
    """
    suspects = []
    for rid, ref in (entry.get("reference") or {}).items():
        pmid, year = ref.get("pmid"), ref.get("year")
        if not pmid or not year:
            continue
        digits = len(str(pmid))
        # PMIDs reached 8 digits around 2000; anything later with 7 or fewer
        # digits, or more than 8 digits at all, does not add up.
        if digits > 8 or (digits <= 7 and int(year) > 2000):
            suspects.append(
                {"reference_id": rid, "pmid": pmid, "year": year, "title": ref.get("title")}
            )
    return suspects


def observations_for_accession(
    entry: dict[str, Any],
    accession: str,
    retrieved_at: str | None = None,
    release: str | None = None,
    skip_reference_ids: set[str] | None = None,
) -> Iterator[Observation]:
    """Yield every BRENDA measurement attached to one UniProt accession."""
    retrieved_at = retrieved_at or _dt.date.today().isoformat()
    skip_reference_ids = skip_reference_ids or set()

    protein_ids = {
        pid
        for pid, protein in (entry.get("protein") or {}).items()
        if accession in (protein.get("accessions") or [])
    }
    if not protein_ids:
        return

    references = entry.get("reference") or {}

    for field, metric in METRICS.items():
        for record in entry.get(field) or []:
            if not protein_ids.intersection(record.get("proteins") or []):
                continue
            value, substrate = _parse_value(record.get("value"))
            if value is None:
                continue

            ref_ids = [
                r for r in (record.get("references") or []) if r not in skip_reference_ids
            ]
            pmid = None
            for rid in ref_ids:
                candidate = references.get(rid, {}).get("pmid")
                if candidate:
                    pmid = str(candidate)
                    break

            conditions = _conditions(record.get("comment") or "")
            if substrate:
                conditions["substrate"] = substrate

            yield Observation(
                metric=metric,
                value=value,
                unit=UNITS.get(metric),
                evidence=Evidence(
                    source_db=SOURCE_DB,
                    retrieved_at=retrieved_at,
                    level="experimental",
                    pmid=pmid,
                    source_version=release,
                ),
                conditions=conditions,
                note=record.get("comment") or None,
            )
