"""Scripted design run. No API key, no network, deterministic.

This exists so the whole system can be demonstrated and tested without a
provider. The script walks a wood/cellulose case through every stage of the
pipeline, including the mandatory gate, and finishes with a report.

Same return shape as LLMClient.chat, so LLMClient delegates to it when
mock=True and nothing downstream can tell the difference.
"""
from __future__ import annotations

from typing import Any

from shared.protocol import ToolCall

_BASE = {
    "k_cat": 3.0, "k_m_uM": 45.0, "half_life_h": 96.0, "t_opt_c": 50.0,
    "t_width_c": 14.0, "ph_opt": 5.0, "ph_width": 1.6, "radius_nm": 3.2,
    "volume_mm3": 8.0, "molar_mass_g_mol": 162.14, "density_g_cm3": 1.5,
    "accessibility": 0.3, "mesh_nm": 20.0, "capture_rate_per_h": 0.6,
    "capture_capacity_umol": 200.0,
}

_WT = {"name": "cellulase-WT", "parent_family": "cellulase", "edits": []}
_V1 = {"name": "cellulase-active_site_", "parent_family": "cellulase",
       "edits": ["active_site_loop_graft"]}

DEFAULT_SCRIPT: list[tuple[str, list[ToolCall]]] = [
    (
        "Starting from the case text. First question is what the fragment is made of - "
        "every downstream choice depends on it, so I will characterize before anything "
        "else and check how confident that identification actually is.",
        [ToolCall(name="characterize_fragment",
                  args={"description": "wood splinter retained in forearm soft tissue, "
                                       "symptomatic, declined surgery",
                        "volume_mm3": 8.0, "anatomy_class": "soft_tissue"})],
    ),
    (
        "Cellulose, confidence 0.75, from the description rather than a sample - worth "
        "stating in the report. Now the chemistry target and the material's own rate "
        "limit.",
        [ToolCall(name="define_reaction",
                  args={"material_family": "cellulose", "surface_state": "crystalline"}),
         ToolCall(name="get_material_notes", args={"material": "cellulose"})],
    ),
    (
        "The note is explicit that accessibility, not turnover, is the binding "
        "constraint here, and that a wood fragment is not sterile. Retrieving families "
        "measured on this substrate, and the precedents with their limits.",
        [ToolCall(name="retrieve_enzymes",
                  args={"query": "beta-1,4-glycosidic hydrolysis of solid crystalline "
                                 "cellulose at physiological temperature",
                        "material": "cellulose", "top_k": 4}),
         ToolCall(name="retrieve_precedents",
                  args={"query": "enzymatic depolymerisation precedent and its limits",
                        "top_k": 3})],
    ),
    (
        "Proposing variants over the documented edit catalogue, biased toward activity "
        "since accessibility is what hurts us. Carrying the wild type so every "
        "engineered candidate has to beat something you could simply buy.",
        [ToolCall(name="propose_variants",
                  args={"parent_family": "cellulase", "n_variants": 4,
                        "goal": "activity", "base_params": _BASE})],
    ),
    (
        "Scoring developability on the two I care about before spending the full assay.",
        [ToolCall(name="predict_properties", args={"candidate": _WT}),
         ToolCall(name="predict_properties", args={"candidate": _V1})],
    ),
    (
        "Running the virtual assay on both: 14 days at 37 C, pH 7.4, 10 percent serum, "
        "inside a 20 nm mesh gel. I want the band, not a point estimate.",
        [ToolCall(name="simulate_hydrogel_assay",
                  args={"candidate": _WT, "base_params": _BASE,
                        "conditions": {"hours": 336.0, "temperature_c": 37.0,
                                       "ph": 7.4, "enzyme_uM": 10.0,
                                       "serum_fraction": 0.1},
                        "product": "cellobiose", "n_samples": 48, "seed": 3})],
    ),
    (
        "Now the engineered variant under identical conditions, same seed, so the "
        "comparison is apples to apples.",
        [ToolCall(name="simulate_hydrogel_assay",
                  args={"candidate": _V1, "base_params": _BASE,
                        "conditions": {"hours": 336.0, "temperature_c": 37.0,
                                       "ph": 7.4, "enzyme_uM": 10.0,
                                       "serum_fraction": 0.1},
                        "product": "cellobiose", "n_samples": 48, "seed": 3})],
    ),
    (
        "Mass balance first - if the books do not close then neither number means "
        "anything - then the full gate battery on the better candidate.",
        [ToolCall(name="check_mass_balance", args={"assay": {}}),
         ToolCall(name="run_safety_gates", args={"assay": {}})],
    ),
    (
        "Gates passed. Ranking, then working out which wet-lab measurement would "
        "remove the most uncertainty.",
        [ToolCall(name="rank_candidates", args={}),
         ToolCall(name="plan_next_experiment", args={"budget": 3})],
    ),
    (
        "Queueing the lead for human review and writing the report.",
        [ToolCall(name="submit_candidate",
                  args={"candidate_name": "cellulase-active_site_",
                        "summary": "Active-site loop graft on a cellulase, simulated "
                                   "against a crystalline cellulose fragment in a "
                                   "product-capturing hydrogel.",
                        "rationale": "Highest simulated erosion rate of the shortlist "
                                     "with all ten gates passed; accessibility remains "
                                     "the binding constraint."})],
    ),
    (
        "Writing up.",
        [ToolCall(name="finish",
                  args={"success": True,
                        "summary": (
                            "SIMULATION HYPOTHESIS - requires wet-lab validation.\n\n"
                            "Case: wood (cellulose) fragment, ~8 mm3, forearm soft "
                            "tissue. Material family identified from the description "
                            "only, confidence 0.75 - a physical sample or spectroscopy "
                            "would raise that and should precede any real work.\n\n"
                            "Chemistry: beta-1,4-glycosidic hydrolysis to cellobiose and "
                            "glucose. Both are ordinary metabolites, which is why this "
                            "material is the most defensible starting point - the "
                            "product-toxicity question is largely answered before we "
                            "begin. Forbidden products for this route are microparticles "
                            "and formaldehyde.\n\n"
                            "Lead candidate: cellulase-active_site_ (active-site loop "
                            "graft). Simulated surface erosion is the highest of the "
                            "shortlist, but read the band rather than the midpoint - it "
                            "is wide, and that width is the honest finding.\n\n"
                            "All ten safety gates passed, including mass-balance closure, "
                            "no appreciable particulate release, and gel capture above "
                            "the threshold. Capture matters more than speed here: a "
                            "faster route that leaked product would have failed.\n\n"
                            "What this does NOT establish: that the designed sequence "
                            "folds, expresses or binds. Nothing here was structurally "
                            "predicted. Published cellulase kinetics are mostly measured "
                            "on milled substrate at the enzyme's own optimum, not on a "
                            "solid splinter at 37 C in serum - closing that gap is the "
                            "actual research question. The fragment is also not sterile, "
                            "and biofilm on the surface would reduce the accessibility "
                            "this model assumes.\n\n"
                            "Next experiments, in priority order, are the three the "
                            "planner returned - each chosen because measuring it would "
                            "most reduce uncertainty about a candidate that could "
                            "plausibly work.")})],
    ),
]


class MockLLM:
    """Replays a script, one step per chat() call."""

    def __init__(self, script: list[tuple[str, list[ToolCall]]] | None = None) -> None:
        self.script = script if script is not None else DEFAULT_SCRIPT
        self.i = 0

    def chat(self, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]]) -> tuple[str, list[ToolCall]]:
        if self.i >= len(self.script):
            return ("Script exhausted.", [ToolCall(
                name="finish",
                args={"success": False,
                      "summary": "Mock script exhausted before reaching a conclusion. "
                                 "This is a harness result, not a scientific one."})])
        thought, calls = self.script[self.i]
        self.i += 1
        return thought, list(calls)
