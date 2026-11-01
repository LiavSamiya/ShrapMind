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

# No kinetics here. The script retrieves them from the warehouse like a real
# run does, so the demo exercises the actual evidence path rather than a set of
# numbers baked into a fixture. bench._resolve_base_params fills them in.
_BASE = {
    "volume_mm3": 8.0,
    "mesh_nm": 20.0,
    "capture_rate_per_h": 0.6,
    "capture_capacity_umol": 200.0,
}

_WT = {"name": "606-WT", "parent_family": "606", "edits": []}
_V1 = {"name": "606-active_site_", "parent_family": "606",
       "edits": ["active_site_loop_graft"]}

DEFAULT_SCRIPT: list[tuple[str, list[ToolCall]]] = [
    (
        "Starting from the case text. First question is what the fragment is made of - "
        "every downstream choice depends on it, so I will characterize before anything "
        "else and check how confident that identification actually is.",
        [ToolCall(name="characterize_fragment",
                  args={"description": "PET polyester fibre fragment retained in "
                                       "forearm soft tissue, symptomatic, surgery declined",
                        "spectra": {"peaks": [1715, 1245]},
                        "volume_mm3": 8.0, "anatomy_class": "soft_tissue"})],
    ),
    (
        "FTIR gives the ester carbonyl at 1715 and the aromatic C-O at 1245, so this is "
        "PET at 0.85 confidence from actual spectral data rather than from the case text. "
        "Now the chemistry target and this material's real rate limit.",
        [ToolCall(name="define_reaction",
                  args={"material_family": "pet", "surface_state": "semi-crystalline"}),
         ToolCall(name="get_material_notes", args={"material": "pet"})],
    ),
    (
        "The note is explicit that crystallinity, not turnover, sets the achievable rate, "
        "and that almost all published PET enzymology was measured at 50-70 C on "
        "amorphous film. Retrieving the curated families for this substrate together "
        "with what the precedents do not establish.",
        [ToolCall(name="retrieve_enzymes",
                  args={"query": "aromatic ester hydrolysis of semi-crystalline PET at "
                                 "physiological temperature",
                        "material": "PET", "top_k": 4}),
         ToolCall(name="retrieve_precedents",
                  args={"query": "enzymatic polyester depolymerisation precedent and "
                                 "its limits", "top_k": 3})],
    ),
    (
        "Retrieval is blunt about the evidence: every candidate's kinetics carry "
        "model-level provenance. I will carry that through rather than quietly "
        "dropping it. Proposing variants over the documented edit catalogue, and "
        "keeping the wild type so any engineered construct has to beat it.",
        [ToolCall(name="propose_variants",
                  args={"parent_family": "606", "n_variants": 3,
                        "goal": "activity", "base_params": _BASE})],
    ),
    (
        "Scoring developability on the two candidates worth the full assay.",
        [ToolCall(name="predict_properties", args={"candidate": _WT}),
         ToolCall(name="predict_properties", args={"candidate": _V1})],
    ),
    (
        "Running the virtual assay on the wild type: 14 days at 37 C, pH 7.4, 10 percent "
        "serum, inside a 20 nm mesh gel. The kinetics come from the warehouse, so the "
        "band will reflect what they were actually measured on.",
        [ToolCall(name="simulate_hydrogel_assay",
                  args={"candidate": _WT, "base_params": _BASE,
                        "conditions": {"hours": 336.0, "temperature_c": 37.0,
                                       "ph": 7.4, "enzyme_uM": 10.0,
                                       "serum_fraction": 0.1},
                        "product": "mhet", "n_samples": 48, "seed": 3})],
    ),
    (
        "Now the engineered variant under identical conditions and the same seed, so the "
        "comparison is apples to apples.",
        [ToolCall(name="simulate_hydrogel_assay",
                  args={"candidate": _V1, "base_params": _BASE,
                        "conditions": {"hours": 336.0, "temperature_c": 37.0,
                                       "ph": 7.4, "enzyme_uM": 10.0,
                                       "serum_fraction": 0.1},
                        "product": "mhet", "n_samples": 48, "seed": 3})],
    ),
    (
        "Mass balance first - if the books do not close then neither number means "
        "anything - then the full gate battery.",
        [ToolCall(name="check_mass_balance", args={"assay": {}}),
         ToolCall(name="run_safety_gates", args={})],
    ),
    (
        "The provenance gate has failed, and it is right to. The turnover number driving "
        "both of those rates was measured on 4-nitrophenyl butanoate - a chromogenic "
        "stand-in - not on PET, and the band is correspondingly wide. That is the "
        "finding. Ranking what I have and working out which measurement would actually "
        "resolve it.",
        [ToolCall(name="rank_candidates", args={}),
         ToolCall(name="plan_next_experiment", args={"budget": 3})],
    ),
    (
        "Writing up. This is a no-go on the evidence, not a candidate recommendation.",
        [ToolCall(name="finish",
                  args={"success": False,
                        "summary": (
                            "SIMULATION HYPOTHESIS - requires wet-lab validation. "
                            "NO CANDIDATE CAN BE RECOMMENDED FROM CURRENT EVIDENCE.\n\n"
                            "Case: PET polyester fragment, ~8 mm3, forearm soft tissue. "
                            "Material identified at 0.85 confidence from FTIR peaks "
                            "(1715 cm-1 ester C=O, 1245 cm-1 aromatic C-O) rather than "
                            "from the case description.\n\n"
                            "Chemistry: aromatic ester hydrolysis to MHET, terephthalic "
                            "acid and ethylene glycol. Ethylene glycol is the product "
                            "that has to be bounded rather than waved past, which is "
                            "what the capture gate is for.\n\n"
                            "Why this run does not produce a recommendation: the "
                            "kinetics-provenance gate failed. The turnover number "
                            "driving the simulated rate was measured on 4-nitrophenyl "
                            "butanoate, a chromogenic stand-in, not on PET. No turnover "
                            "number measured on a solid polymer fragment exists anywhere "
                            "in the knowledge base - of 289 kinetic measurements across "
                            "505 curated enzymes, 168 are on model esters, 42 on soluble "
                            "oligomers, and none on the real material. The predictive-"
                            "confidence gate failed for the same underlying reason: once "
                            "the band is widened to reflect that provenance it spans "
                            "roughly an order of magnitude, which cannot support a "
                            "recommendation.\n\n"
                            "Mass balance closed, capture cleared its threshold and no "
                            "appreciable particulate was released, so the formulation "
                            "side of the model is behaving. The blocker is the evidence, "
                            "not the chemistry.\n\n"
                            "What this does NOT establish: that these enzymes cannot "
                            "work on PET at body temperature. It establishes that nobody "
                            "has measured whether they do. Published PET enzymology is "
                            "almost entirely at 50-70 C on amorphous film; this case is "
                            "37 C on semi-crystalline fibre in serum, and closing that "
                            "gap is the actual research question.\n\n"
                            "The single most valuable next step is therefore a wet-lab "
                            "turnover measurement on real PET substrate at 37 C in "
                            "serum, for the candidates the planner ranked - which is "
                            "exactly what would let this gate pass.")})],
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
