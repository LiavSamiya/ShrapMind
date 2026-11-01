"""The bench facade: what the agent loop calls instead of talking to a worker.

Method names match tool names exactly, because dispatch is
`getattr(bench, name)`. Two kinds of method live here:

  - proxied: forwarded to the simulation worker over the bridge. Anything
    CPU-bound or numerical.
  - local: answered here without a round trip. Database retrieval (the DB is
    on the backend, not the worker), pure bookkeeping, and the two tools that
    only exist to produce a UI event.

Per-tool timeouts are the only customization. A full uncertainty sweep can
legitimately take minutes, and a timeout that is too tight shows up as a
mysterious "worker disconnected" rather than as the slow call it is.
"""
from __future__ import annotations

import logging
from typing import Any

from server.app.bridge import bridge

log = logging.getLogger("shrapmind.bench")

# Generous where the work is real, tight where it is not.
_TIMEOUTS: dict[str, float] = {
    "characterize_fragment": 30.0,
    "define_reaction": 15.0,
    "propose_variants": 30.0,
    "predict_properties": 20.0,
    "score_kinetics": 90.0,
    "simulate_hydrogel_assay": 300.0,
    "check_mass_balance": 20.0,
    "run_safety_gates": 30.0,
    "plan_next_experiment": 30.0,
    "wait": 12.0,
}


class Bench:
    """One design session's view of the world."""

    def __init__(self, client_id: str = "default", *, skip_db: bool = False,
                 mode: str = "run", presentation: str | None = None,
                 case_text: str = "") -> None:
        self.client_id = client_id
        self.skip_db = skip_db
        self.mode = mode
        # The user's explicit presentation choice, if they made one. It wins
        # over whatever the model passes, because it is a statement about the
        # case rather than a modelling decision.
        self.presentation = presentation
        # The original case text, forwarded to characterisation so presentation
        # inference sees the whole case rather than only the model's paraphrase.
        self.case_text = case_text
        # Full evidence records for the families retrieved this session, so
        # base_params_for() can hand the simulator measured values + citations.
        self._evidence: dict[str, Any] = {}
        # Accumulated session state. This is what gets serialized into every
        # turn's message - the agent's equivalent of "the current screen".
        self.state: dict[str, Any] = {
            "passport": None,
            "reaction_spec": None,
            "substrate": None,
            "families": [],
            "precedents": [],
            "candidates": [],
            "properties": {},
            "assays": {},
            "gates": {},
            "ranking": [],
            "next_experiments": [],
            "submitted": [],
        }

    # ------------------------------------------------------------- transport

    def _call(self, name: str, args: dict[str, Any] | None = None,
              timeout: float | None = None) -> Any:
        return bridge.call_sync(self.client_id, name, args or {},
                                timeout=timeout or _TIMEOUTS.get(name, 60.0))

    # ------------------------------------------------------------- proxied

    def characterize_fragment(self, description: str = "", spectra: dict | None = None,
                              volume_mm3: float | None = None,
                              anatomy_class: str = "soft_tissue",
                              presentation: str | None = None,
                              particle_size_um: float | None = None,
                              retrievable_mechanically: bool | None = None) -> Any:
        r = self._call("characterize_fragment", {
            "description": description, "spectra": spectra,
            "volume_mm3": volume_mm3, "anatomy_class": anatomy_class,
            "presentation": self.presentation or presentation,
            "particle_size_um": particle_size_um,
            "retrievable_mechanically": retrievable_mechanically,
            "case_text": self.case_text})
        if isinstance(r, dict) and r.get("passport"):
            self.state["passport"] = r["passport"]
        return r

    def define_reaction(self, material_family: str, surface_state: str = "unknown") -> Any:
        r = self._call("define_reaction", {"material_family": material_family,
                                           "surface_state": surface_state})
        if isinstance(r, dict) and r.get("ok"):
            self.state["reaction_spec"] = r.get("reaction_spec")
            self.state["substrate"] = r.get("substrate")
        return r

    def propose_variants(self, parent_family: str, base_params: dict | None = None,
                         n_variants: int = 5, goal: str = "balanced") -> Any:
        r = self._call("propose_variants", {
            "parent_family": parent_family, "base_params": base_params,
            "n_variants": n_variants, "goal": goal})
        if isinstance(r, dict) and r.get("candidates"):
            self.state["candidates"] = r["candidates"]
        return r

    def predict_properties(self, candidate: dict) -> Any:
        r = self._call("predict_properties", {"candidate": candidate})
        if isinstance(r, dict) and r.get("name"):
            self.state["properties"][r["name"]] = r.get("scores", {})
        return r

    def _resolve_base_params(self, candidate: dict,
                             base_params: dict | None) -> dict[str, Any]:
        """Fill in measured kinetics from the retrieved evidence.

        The model should not have to echo k_cat, K_m and a citation list back
        through a tool argument: that wastes tokens, invites truncation, and
        gives it the opportunity to "tidy" a number. If the caller did not
        supply kinetics, look them up from what retrieve_enzymes returned for
        this candidate's parent family (or its own name).

        Anything the caller DID supply wins, so an explicit what-if is still
        possible - it just has to be explicit.
        """
        base = dict(base_params or {})
        # Geometry comes from the passport, always. The model established the
        # presentation and particle size at characterisation; making it repeat
        # them through every simulate call is how they end up inconsistent
        # between candidates in the same run.
        pp = self.state.get("passport") or {}
        for key in ("presentation", "particle_size_um", "volume_mm3"):
            if base.get(key) is None and pp.get(key) is not None:
                base[key] = pp[key]
        sub = self.state.get("substrate") or {}
        for key in ("molar_mass_g_mol", "density_g_cm3", "accessibility"):
            if base.get(key) is None and sub.get(key) is not None:
                base[key] = sub[key]
        if base.get("k_cat") is not None:
            return base
        for key in (candidate.get("parent_family"), candidate.get("name")):
            if not key:
                continue
            found = self.base_params_for(str(key))
            if found:
                # Caller-supplied values take precedence over the warehouse,
                # but the host-safety screen is not overridable - it is not an
                # input, it is a property of the protein.
                merged = {**found, **{k: v for k, v in base.items() if v is not None}}
                merged["enzyme_safety"] = self.enzyme_safety_for(str(key))
                return merged
        return base

    def score_kinetics(self, candidate: dict, base_params: dict | None = None,
                       conditions: dict | None = None, product: str = "oligomer") -> Any:
        return self._call("score_kinetics", {
            "candidate": candidate,
            "base_params": self._resolve_base_params(candidate, base_params),
            "conditions": conditions, "product": product})

    def simulate_hydrogel_assay(self, candidate: dict, base_params: dict | None = None,
                                conditions: dict | None = None, product: str = "oligomer",
                                n_samples: int = 64, seed: int = 0) -> Any:
        r = self._call("simulate_hydrogel_assay", {
            "candidate": candidate,
            "base_params": self._resolve_base_params(candidate, base_params),
            "conditions": conditions,
            "product": product, "n_samples": n_samples, "seed": seed})
        if isinstance(r, dict) and r.get("candidate"):
            self.state["assays"][r["candidate"]] = r
        return r

    def _resolve_assay(self, assay: dict | None) -> dict:
        """Let the model say "the assay" without re-pasting it.

        A 60-point time series is not something to make the model echo back
        through a tool argument - it would burn tokens, invite truncation and
        give it the chance to "helpfully" alter a number. An empty or
        name-only argument resolves to the stored result; a dict that already
        carries metrics is passed through untouched.
        """
        if isinstance(assay, dict) and assay.get("mass_balance_residual") is not None:
            return assay
        name = (assay or {}).get("candidate") if isinstance(assay, dict) else None
        if name and name in self.state["assays"]:
            return self.state["assays"][name]
        if self.state["assays"]:
            # Most recently simulated candidate.
            return list(self.state["assays"].values())[-1]
        return assay if isinstance(assay, dict) else {}

    def check_mass_balance(self, assay: dict | None = None, tolerance: float = 1e-6) -> Any:
        resolved = self._resolve_assay(assay)
        if not resolved:
            return {"error": "no assay to check - run simulate_hydrogel_assay first"}
        return self._call("check_mass_balance", {"assay": resolved, "tolerance": tolerance})

    def run_safety_gates(self, assay: dict | None = None, reaction_spec: dict | None = None,
                         passport: dict | None = None, candidate: dict | None = None) -> Any:
        resolved = self._resolve_assay(assay)
        if not resolved:
            return {"error": "no assay to gate - run simulate_hydrogel_assay first"}
        r = self._call("run_safety_gates", {
            "assay": resolved,
            "reaction_spec": reaction_spec or self.state.get("reaction_spec") or {},
            "passport": passport or self.state.get("passport") or {},
            "candidate": candidate})
        name = resolved.get("candidate") or (candidate or {}).get("name")
        if isinstance(r, dict) and name:
            self.state["gates"][name] = r
        return r

    def plan_next_experiment(self, assays: list | None = None, budget: int = 3) -> Any:
        if assays is None:
            assays = []
            for name, a in self.state["assays"].items():
                g = self.state["gates"].get(name, {})
                assays.append({**a, "gates_passed": bool(g.get("passed"))})
        r = self._call("plan_next_experiment", {"assays": assays, "budget": budget})
        if isinstance(r, dict):
            self.state["next_experiments"] = r.get("experiments", [])
        return r

    def wait(self, seconds: float = 1.0) -> Any:
        return self._call("wait", {"seconds": seconds})

    # ------------------------------------------------------------- local

    def read_passport(self) -> Any:
        """Return the current bench state. Answered locally - no round trip."""
        return {
            "passport": self.state["passport"],
            "reaction_spec": self.state["reaction_spec"],
            "n_candidates": len(self.state["candidates"]),
            "n_assays": len(self.state["assays"]),
            "gates": {k: v.get("passed") for k, v in self.state["gates"].items()},
        }

    def get_material_notes(self, material: str) -> Any:
        """Lazy per-material guidance. DB first, in-process copy as fallback."""
        from server.agent.notes import get_notes

        note = get_notes(material, self.mode)
        if not self.skip_db:
            try:
                from server.db.client import get_material_notes as db_notes

                table = db_notes(self.mode)
                for family, text in table.items():
                    if family in (material or "").lower() and text:
                        note = text
                        break
            except Exception as e:  # noqa: BLE001
                log.info("material notes from memory (%s)", e)
        return {"material": material, "note": note}

    def retrieve_enzymes(self, query: str, material: str | None = None,
                         top_k: int = 5) -> Any:
        """Search the evidence warehouse for candidate enzyme families.

        Reads the committed f2c warehouse directly, so real evidence - with
        citations and with the substrate each constant was measured on - is
        available even when Postgres is not. Postgres adds semantic search at
        scale; it is not required to get real data.

        An uncovered material returns an explicit empty result naming the
        materials that ARE covered. That is the honest answer and it is far
        more useful than a plausible placeholder, which is what this used to
        return.
        """
        try:
            from server.db.evidence import index

            idx = index()
        except Exception as e:  # noqa: BLE001
            return {"families": [], "error": f"evidence warehouse unavailable: {e}"}

        # f2c's own objection for materials with no enzymatic route at all.
        if material:
            blocked = idx.blocked_reason(material)
            if blocked:
                return {"families": [], "n": 0, "blocked": True,
                        "blocked_reason": blocked,
                        "note": "This material has no enzymatic degradation route. "
                                "Report that as the finding."}

        hits = idx.search(query, material=material, top_k=top_k)
        if not hits and material:
            covered = sorted(idx.by_material)
            return {
                "families": [], "n": 0,
                "note": f"No enzymes in this knowledge base are curated for "
                        f"{material!r}. Covered materials: {', '.join(covered)}. "
                        f"Do not substitute a candidate from another material - "
                        f"report the gap.",
                "covered_materials": covered,
            }

        unsafe = [h.name for h in hits if h.safety and h.safety.blocking]
        self.state["families"] = [h.to_dict() for h in hits]
        # Keep the full records so simulate can lift measured parameters, and
        # the citations travel with them.
        self._evidence = {h.name: h for h in hits}
        out: dict[str, Any] = {
            "families": self.state["families"],
            "n": len(hits),
            "snapshot": idx.built_at,
            "note": "`kinetics_provenance` says what each constant was measured "
                    "on. Nothing in this knowledge base was measured on a solid "
                    "fragment, so pass base_params from these records rather than "
                    "inventing values, and expect the provenance gate to bite.",
        }
        if unsafe:
            out["host_unsafe_candidates"] = unsafe
            out["warning"] = (
                f"HOST SAFETY: {', '.join(unsafe)} would act on human tissue, "
                f"not only on the fragment. Each one's `enzyme_safety` field "
                f"names the host substrate at risk. These are listed last and "
                f"must not be selected: the gate battery will refuse them, and "
                f"an enzyme that digests the tissue holding the wound together "
                f"is worse than leaving the fragment in place.")
        return out

    def base_params_for(self, family_name: str) -> dict[str, Any]:
        """Measured parameters for one retrieved family, ready for the
        simulator. Only measured values; the rest are reported as assumed."""
        ev = getattr(self, "_evidence", {})
        rec = ev.get(family_name)
        if rec is None:
            key = str(family_name).strip().lower()
            rec = next((v for k, v in ev.items() if k.strip().lower() == key), None)
        if rec is None:
            return {}
        out = rec.to_base_params()
        kcat = rec.measured.get("kcat")
        if kcat is not None:
            out["measured_on"] = kcat.substrate_name or "an unrecorded substrate"
        return out

    def enzyme_safety_for(self, family_name: str) -> dict[str, Any]:
        """Host-safety screen for one retrieved family."""
        ev = getattr(self, "_evidence", {})
        rec = ev.get(family_name)
        if rec is None:
            key = str(family_name).strip().lower()
            rec = next((v for k, v in ev.items() if k.strip().lower() == key), None)
        return rec.safety.to_dict() if (rec and rec.safety) else {}

    def retrieve_precedents(self, query: str, top_k: int = 3) -> Any:
        """Literature precedents, carrying what each does NOT prove."""
        if self.skip_db:
            return {"precedents": [], "note": "database skipped (SKIP_DB)"}
        try:
            from server.db.client import search_precedents

            hits = search_precedents(query, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            return {"precedents": [], "error": f"retrieval unavailable: {e}"}
        self.state["precedents"] = [h.model_dump() for h in hits]
        return {"precedents": self.state["precedents"], "n": len(hits)}

    def _warehouse_coverage(self) -> dict[str, Any]:
        """What the knowledge base covers, for the report and /health."""
        try:
            from server.db.evidence import index

            return index().coverage()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def rank_candidates(self, weights: dict[str, float] | None = None) -> Any:
        """Multi-objective ranking over whatever has been simulated so far.

        Pareto front first, then a weighted score inside it. Candidates whose
        gates failed are listed but never ranked above a passing one - the
        ranking is not allowed to trade safety off against rate.
        """
        w = {"erosion": 0.4, "developability": 0.3, "confidence": 0.3}
        for k, v in (weights or {}).items():
            if k in w:
                try:
                    w[k] = float(v)
                except (TypeError, ValueError):
                    pass
        total = sum(w.values()) or 1.0
        w = {k: v / total for k, v in w.items()}

        rows: list[dict[str, Any]] = []
        rates = [a.get("erosion_rate_um_per_day", 0.0) for a in self.state["assays"].values()]
        max_rate = max(rates) if rates else 1.0
        for name, a in self.state["assays"].items():
            gates = self.state["gates"].get(name, {})
            props = self.state["properties"].get(name, {})
            unc = float(a.get("uncertainty", 99.0))
            # "not gated" is a different statement from "failed", and a
            # reviewer needs to be able to tell them apart: one is a verdict,
            # the other is an unfinished job.
            if not gates:
                gate_status = "not_gated"
            elif gates.get("passed"):
                gate_status = "pass"
            else:
                gate_status = "fail"
            rows.append({
                "candidate": name,
                "gate_status": gate_status,
                "erosion_rate_um_per_day": a.get("erosion_rate_um_per_day", 0.0),
                "erosion_rate_ci": a.get("erosion_rate_ci"),
                "captured_fraction": a.get("captured_fraction"),
                "uncertainty": unc,
                "developability": props.get("developability"),
                "gates_passed": bool(gates.get("passed")),
                "failed_gates": gates.get("failed", []),
                "score": round(
                    w["erosion"] * (float(a.get("erosion_rate_um_per_day", 0.0)) / (max_rate or 1.0))
                    + w["developability"] * float(props.get("developability") or 0.0)
                    + w["confidence"] * (1.0 / (1.0 + unc)), 4),
            })
        # Gate status is the primary sort key, not a tiebreak.
        _order = {"pass": 2, "not_gated": 1, "fail": 0}
        rows.sort(key=lambda r: (_order[r["gate_status"]], r["score"]), reverse=True)
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        self.state["ranking"] = rows
        return {
            "ranking": rows,
            "weights": w,
            "note": "Candidates that failed a safety gate are never ranked above "
                    "one that passed, whatever their rate. 'not_gated' means "
                    "run_safety_gates has not been run on it yet - that is an "
                    "unfinished job, not a verdict.",
        }

    def highlight_step(self, stage: str, label: str = "", detail: str = "") -> Any:
        """Explain-mode annotation. Produces a UI event and nothing else -
        this is the tool that lets the agent teach the pipeline without
        consuming worker compute."""
        return {"stage": stage, "label": label, "detail": detail, "annotated": True}

    def submit_candidate(self, candidate_name: str, summary: str,
                         rationale: str = "") -> Any:
        """Queue a candidate for human scientific review."""
        name = candidate_name
        assay = self.state["assays"].get(name, {})
        gates = self.state["gates"].get(name, {})
        if not gates:
            return {"error": f"no safety gates have been run for {name!r} - "
                             f"run run_safety_gates before submitting"}
        if not gates.get("passed"):
            return {"error": f"{name!r} failed these gates: "
                             f"{', '.join(gates.get('failed', []))}. A failing "
                             f"candidate cannot be submitted for promotion."}
        cand = next((c for c in self.state["candidates"] if c.get("name") == name), {})
        if self.skip_db:
            self.state["submitted"].append(name)
            return {"queued": False, "note": "database skipped (SKIP_DB) - not persisted",
                    "candidate": name}
        try:
            from server.db.client import submit_pending_candidate

            res = submit_pending_candidate(
                "add", name, summary,
                material_family=(self.state.get("passport") or {}).get("material_family", ""),
                rationale=rationale, candidate=cand, assay=assay,
                gates=gates.get("gates", []), submitted_by="agent")
        except Exception as e:  # noqa: BLE001
            return {"error": f"could not queue for review: {e}"}
        self.state["submitted"].append(name)
        return {"queued": True, "pending_id": res["id"], "candidate": name,
                "note": "Queued for human scientific review. It does not enter the "
                        "validated library until a reviewer approves it."}

    def finish(self, summary: str, success: bool = True) -> Any:
        """Answered locally. The loop's own finish guards do the real work."""
        return {"summary": summary, "success": bool(success)}
