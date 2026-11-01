"""Seed the knowledge base.

Two tables carry real content:

  enzyme_families  - a small, hand-checked set of families with kinetic
                     records and, critically, THE CONDITIONS THEY WERE
                     MEASURED UNDER. A k_cat without its assay temperature is
                     not evidence, and the agent is instructed to say so.
                     This is the table scripts/ingest_brenda.py would fill in
                     bulk; the seed makes the system useful before any import.

  precedents       - the "precedent, not science fiction" table from the
                     project's own concept brief, with both halves of each
                     claim. what_it_does_not_prove is the column that keeps
                     the pitch honest.

Numbers here are order-of-magnitude values drawn from the published work the
concept brief cites. They are seed values for a simulator, not measurements
of any candidate this system designs. Treat every one as a placeholder to be
replaced by a real record during ingestion.

Destructive re-seed. Run as: python -m server.db.seed
"""
from __future__ import annotations

import sys
from typing import Any

from server.agent.notes import MATERIAL_NOTES

# ---------------------------------------------------------------- families

FAMILIES: list[dict[str, Any]] = [
    {
        "name": "cellulase (endoglucanase, GH5)",
        "ec_class": "EC 3.2.1.4",
        "reaction_class": "beta-1,4-glycosidic hydrolysis",
        "substrate_material": "cellulose",
        "kinetics": {"k_cat": 3.0, "k_m_uM": 45.0, "t_opt_c": 50.0,
                     "t_width_c": 14.0, "ph_opt": 5.0, "ph_width": 1.6,
                     "ea_kj": 45.0, "radius_nm": 3.2, "half_life_h": 96.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 50.0, "measured_ph": 5.0,
                       "substrate_form": "amorphous / milled",
                       "serum": False,
                       "caveat": "Measured well away from body conditions and on "
                                 "milled substrate. Activity on a solid splinter at "
                                 "37 C and pH 7.4 is the open question."},
        "maturity": "flagship",
        "source": "industrial cellulase literature; see concept brief refs",
    },
    {
        "name": "cellobiohydrolase (GH7)",
        "ec_class": "EC 3.2.1.91",
        "reaction_class": "beta-1,4-glycosidic hydrolysis, processive from chain end",
        "substrate_material": "cellulose",
        "kinetics": {"k_cat": 0.8, "k_m_uM": 20.0, "t_opt_c": 50.0,
                     "t_width_c": 12.0, "ph_opt": 5.0, "ph_width": 1.4,
                     "ea_kj": 48.0, "radius_nm": 4.0, "half_life_h": 72.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 50.0, "measured_ph": 5.0,
                       "substrate_form": "crystalline",
                       "serum": False,
                       "caveat": "Slower than endoglucanase but works on crystalline "
                                 "regions, which is where the mass actually is. "
                                 "Realistically a cocktail component, not a soloist."},
        "maturity": "flagship",
        "source": "cellulase synergism literature",
    },
    {
        "name": "beta-glucosidase (GH1)",
        "ec_class": "EC 3.2.1.21",
        "reaction_class": "cellobiose to glucose hydrolysis",
        "substrate_material": "cellulose",
        "kinetics": {"k_cat": 12.0, "k_m_uM": 120.0, "t_opt_c": 45.0,
                     "t_width_c": 13.0, "ph_opt": 6.0, "ph_width": 1.5,
                     "ea_kj": 40.0, "radius_nm": 3.0, "half_life_h": 60.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 45.0, "measured_ph": 6.0,
                       "substrate_form": "soluble",
                       "serum": False,
                       "caveat": "Acts on the soluble product, not on the fragment. "
                                 "Its role is relieving product inhibition of the "
                                 "upstream enzymes, not eroding anything."},
        "maturity": "flagship",
        "source": "cellulase cocktail literature",
    },
    {
        "name": "PETase (IsPETase-type)",
        "ec_class": "EC 3.1.1.101",
        "reaction_class": "aromatic ester hydrolysis",
        "substrate_material": "pet",
        "kinetics": {"k_cat": 0.6, "k_m_uM": 90.0, "t_opt_c": 40.0,
                     "t_width_c": 8.0, "ph_opt": 8.0, "ph_width": 1.2,
                     "ea_kj": 52.0, "radius_nm": 2.8, "half_life_h": 36.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 40.0, "measured_ph": 8.0,
                       "substrate_form": "amorphous film",
                       "serum": False,
                       "caveat": "Nearly all published PET enzymology is on amorphous "
                                 "film, not semi-crystalline fibre. Crystallinity, not "
                                 "k_cat, sets the achievable rate."},
        "maturity": "benchmark",
        "source": "Yoshida et al. 2016; see concept brief refs",
    },
    {
        "name": "FAST-PETase (engineered variant)",
        "ec_class": "EC 3.1.1.101",
        "reaction_class": "aromatic ester hydrolysis",
        "substrate_material": "pet",
        "kinetics": {"k_cat": 2.4, "k_m_uM": 70.0, "t_opt_c": 50.0,
                     "t_width_c": 10.0, "ph_opt": 8.0, "ph_width": 1.2,
                     "ea_kj": 50.0, "radius_nm": 2.8, "half_life_h": 96.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 50.0, "measured_ph": 8.0,
                       "substrate_form": "amorphous film",
                       "serum": False,
                       "caveat": "A genuine engineering success and a good precedent "
                                 "for the design loop. Still measured at 50 C in "
                                 "buffer, and pH 8 optimum sits above tissue pH."},
        "maturity": "benchmark",
        "source": "Lu et al., Nature 2022",
    },
    {
        "name": "MHETase",
        "ec_class": "EC 3.1.1.102",
        "reaction_class": "MHET to terephthalate + ethylene glycol hydrolysis",
        "substrate_material": "pet",
        "kinetics": {"k_cat": 8.0, "k_m_uM": 60.0, "t_opt_c": 40.0,
                     "t_width_c": 9.0, "ph_opt": 7.5, "ph_width": 1.2,
                     "ea_kj": 44.0, "radius_nm": 3.6, "half_life_h": 48.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 40.0, "measured_ph": 7.5,
                       "substrate_form": "soluble MHET",
                       "serum": False,
                       "caveat": "Downstream partner to PETase. Releases ethylene "
                                 "glycol, which is the product the capture gate exists "
                                 "for - bound it explicitly rather than assuming it is "
                                 "harmless at these quantities."},
        "maturity": "benchmark",
        "source": "Yoshida et al. 2016",
    },
    {
        "name": "cellulase cocktail (cotton-adapted)",
        "ec_class": "EC 3.2.1.4 / 3.2.1.91",
        "reaction_class": "beta-1,4-glycosidic hydrolysis of high-crystallinity cellulose",
        "substrate_material": "cotton",
        "kinetics": {"k_cat": 1.2, "k_m_uM": 55.0, "t_opt_c": 50.0,
                     "t_width_c": 13.0, "ph_opt": 5.0, "ph_width": 1.5,
                     "ea_kj": 46.0, "radius_nm": 3.4, "half_life_h": 80.0,
                     "fragmentation_fraction": 0.0},
        "conditions": {"measured_at_c": 50.0, "measured_ph": 5.0,
                       "substrate_form": "woven cotton",
                       "serum": False,
                       "caveat": "Crystallinity is the binding constraint. Clean "
                                 "results on undyed cotton say nothing about dyed or "
                                 "finished fabric."},
        "maturity": "benchmark",
        "source": "textile biopolishing literature",
    },
    {
        "name": "[FeFe]-hydrogenase (biocorrosion-associated)",
        "ec_class": "EC 1.12.7.2",
        "reaction_class": "Fe(0) oxidation via extracellular electron uptake",
        "substrate_material": "iron_steel",
        "kinetics": {"k_cat": 0.02, "k_m_uM": 300.0, "t_opt_c": 35.0,
                     "t_width_c": 8.0, "ph_opt": 7.0, "ph_width": 1.0,
                     "ea_kj": 58.0, "radius_nm": 4.5, "half_life_h": 18.0,
                     "fragmentation_fraction": 0.004},
        "conditions": {"measured_at_c": 30.0, "measured_ph": 7.0,
                       "substrate_form": "mild steel coupon",
                       "serum": False,
                       "oxygen": "anaerobic",
                       "caveat": "Documented but slow, and measured anaerobically. "
                                 "Passivation and oxygen availability dominate. The "
                                 "reaction liberates ions rather than metabolites, so "
                                 "capture - not rate - decides whether it is viable."},
        "maturity": "research",
        "source": "Rouvre & Basseguy 2016; Deutzmann et al. 2018",
    },
    {
        "name": "[NiFe]-hydrogenase (extracellular)",
        "ec_class": "EC 1.12.2.1",
        "reaction_class": "Fe(0) oxidation via extracellular electron uptake",
        "substrate_material": "iron_steel",
        "kinetics": {"k_cat": 0.035, "k_m_uM": 250.0, "t_opt_c": 37.0,
                     "t_width_c": 9.0, "ph_opt": 7.2, "ph_width": 1.1,
                     "ea_kj": 55.0, "radius_nm": 5.0, "half_life_h": 24.0,
                     "fragmentation_fraction": 0.004},
        "conditions": {"measured_at_c": 37.0, "measured_ph": 7.2,
                       "substrate_form": "mild steel coupon",
                       "serum": False,
                       "oxygen": "anaerobic",
                       "caveat": "Closer to body temperature than most records here, "
                                 "but still anaerobic and still very slow. A larger "
                                 "enzyme, so mesh hindrance cuts further into the rate."},
        "maturity": "research",
        "source": "Deutzmann et al. 2018",
    },
    {
        "name": "polyurethane esterase",
        "ec_class": "EC 3.1.1.-",
        "reaction_class": "carbamate / ester hydrolysis",
        "substrate_material": "polyurethane",
        "kinetics": {"k_cat": 0.3, "k_m_uM": 150.0, "t_opt_c": 40.0,
                     "t_width_c": 10.0, "ph_opt": 7.0, "ph_width": 1.3,
                     "ea_kj": 50.0, "radius_nm": 3.1, "half_life_h": 40.0,
                     "fragmentation_fraction": 0.02},
        "conditions": {"measured_at_c": 40.0, "measured_ph": 7.0,
                       "substrate_form": "polyester-PU film",
                       "serum": False,
                       "caveat": "Aromatic amine release is a hard blocker. The "
                                 "product panel is the gate here, not the kinetics."},
        "maturity": "research",
        "source": "polyurethanase literature",
    },
]

# ---------------------------------------------------------------- precedents

PRECEDENTS: list[dict[str, Any]] = [
    {
        "title": "ProGen - functional artificial lysozymes",
        "claim": "A language model generated novel, functional enzyme sequences.",
        "what_it_proves": "A new sequence can be generated inside a known functional "
                          "family and still work, down to 31.4% identity to any "
                          "natural protein.",
        "what_it_does_not_prove": "Not a wholly new reaction, and not one-shot - "
                                  "screening was required. Generating a sequence is "
                                  "not the same as getting a working catalyst.",
        "citation": "Madani et al., Nature Biotechnology 2023",
    },
    {
        "title": "LuxSit - de novo luciferase",
        "claim": "A complete digital-to-protein chain produced a working enzyme for a "
                 "synthetic substrate.",
        "what_it_proves": "The full design-build-test chain can work end to end.",
        "what_it_does_not_prove": "Three hits from 7,648 initial designs. It "
                                  "demonstrates the cost of the search as much as the "
                                  "capability - most designs are not active enzymes.",
        "citation": "Yeh et al., Nature 2023",
    },
    {
        "title": "RFdiffusion - designed structures and metal binders",
        "claim": "Scaffolds and binding function can be generated from a specification.",
        "what_it_proves": "Geometry and binding can be designed to order.",
        "what_it_does_not_prove": "Requires a precise chemical specification to aim "
                                  "at. It does not tell you what reaction to target, "
                                  "which is the harder half of this problem.",
        "citation": "Watson et al., Nature 2023",
    },
    {
        "title": "RFdiffusion2 - enzymes from three mechanisms",
        "claim": "Active sites were designed for several distinct mechanisms.",
        "what_it_proves": "Mechanism-directed active-site design is feasible.",
        "what_it_does_not_prove": "Still needed on the order of 96 tests per campaign. "
                                  "Not every design is an active enzyme.",
        "citation": "Bauer et al., Nature Methods 2026",
    },
    {
        "title": "ZETA - de novo metallohydrolases",
        "claim": "New active sites with a metal cofactor reached 53,000 M-1 s-1.",
        "what_it_proves": "A new active site incorporating a metal can be designed.",
        "what_it_does_not_prove": "It does not dissolve solid metal. Of 96 designs "
                                  "tested, 86 were soluble and five were active - and "
                                  "none of this was shown in tissue or in a device.",
        "citation": "Kim et al., Nature 2025",
    },
    {
        "title": "FAST-PETase - engineered polyester hydrolysis",
        "claim": "A machine-learning-guided variant depolymerised PET far faster than "
                 "the wild type.",
        "what_it_proves": "Model-guided engineering measurably improves a real "
                          "polymer-degrading enzyme.",
        "what_it_does_not_prove": "Demonstrated at elevated temperature on amorphous "
                                  "substrate in buffer, not at 37 C on crystalline "
                                  "fibre in serum. That gap is this project's research "
                                  "question, not a detail.",
        "citation": "Lu et al., Nature 2022",
    },
    {
        "title": "Hydrogenase-accelerated steel corrosion",
        "claim": "Hydrogenases accelerated Fe(0) oxidation under near-neutral "
                 "conditions.",
        "what_it_proves": "There is a mechanistic anchor for the metal route: enzymes "
                          "can participate in iron oxidation.",
        "what_it_does_not_prove": "Shown anaerobically on steel coupons, never in "
                                  "tissue or as a therapeutic device, and slowly. It "
                                  "liberates ions, which is a containment problem "
                                  "rather than a rate problem.",
        "citation": "Rouvre & Basseguy 2016; Deutzmann et al. 2018",
    },
    {
        "title": "Injectable in-situ gelling hydrogels for protein delivery",
        "claim": "FDA-approved injectable hydrogels gel at body temperature and hold "
                 "protein payloads.",
        "what_it_proves": "The delivery vehicle is not speculative - over 30 injectable "
                          "hydrogel products are approved, and in-situ gelation and "
                          "protein retention are established.",
        "what_it_does_not_prove": "None was designed to capture the products of a "
                                  "reaction happening inside it. Capture capacity, ion "
                                  "retention and non-swelling behaviour next to a "
                                  "nerve all remain to be demonstrated.",
        "citation": "SpaceOAR / Jelmyto and injectable-hydrogel literature",
    },
    {
        "title": "Retained-fragment clinical decision making",
        "claim": "Most retained fragments are managed conservatively; removal carries "
                 "its own risk.",
        "what_it_proves": "The gap this project targets is real: there is no middle "
                          "option between watchful waiting and surgery.",
        "what_it_does_not_prove": "It does not show that enzymatic erosion is a safe "
                                  "or effective third option. That is unproven, and "
                                  "nothing in this system changes that.",
        "citation": "Riehl et al.; Nee et al. 2021",
    },
    {
        "title": "Fragment material heterogeneity",
        "claim": "Embedded fragments vary widely in composition, including trace "
                 "metals and additives.",
        "what_it_proves": "Per-case material identification is necessary - 'metal' or "
                          "'plastic' is not a specification you can design against.",
        "what_it_does_not_prove": "It does not establish that any given fragment can "
                                  "be identified non-invasively with enough confidence "
                                  "to design against.",
        "citation": "Centeno et al. 2014; Negoduyko et al. 2019",
    },
]


def main() -> int:
    import json

    from server.db.client import _connect, _vec_literal, embed

    with _connect() as conn, conn.cursor() as cur:
        print("clearing seeded tables...")
        cur.execute("delete from enzyme_families")
        cur.execute("delete from precedents")
        cur.execute("delete from material_notes")

        for f in FAMILIES:
            text = (f"{f['name']} {f['ec_class']} {f['reaction_class']} "
                    f"substrate {f['substrate_material']}")
            cur.execute("""
                insert into enzyme_families
                    (name, ec_class, reaction_class, substrate_material, kinetics,
                     conditions, maturity, source, embedding)
                values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::vector)
            """, (f["name"], f["ec_class"], f["reaction_class"],
                  f["substrate_material"], json.dumps(f["kinetics"]),
                  json.dumps(f["conditions"]), f["maturity"], f["source"],
                  _vec_literal(embed(text))))
            print(f"  family: {f['name']}")

        for p in PRECEDENTS:
            text = f"{p['title']} {p['claim']} {p['what_it_proves']}"
            cur.execute("""
                insert into precedents
                    (title, claim, what_it_proves, what_it_does_not_prove, citation,
                     embedding)
                values (%s,%s,%s,%s,%s,%s::vector)
            """, (p["title"], p["claim"], p["what_it_proves"],
                  p["what_it_does_not_prove"], p["citation"],
                  _vec_literal(embed(text))))
            print(f"  precedent: {p['title']}")

        for material, notes in MATERIAL_NOTES.items():
            cur.execute("""
                insert into material_notes (material, run_note, explain_note)
                values (%s,%s,%s)
                on conflict (material) do update
                set run_note = excluded.run_note, explain_note = excluded.explain_note
            """, (material, notes["run_note"], notes["explain_note"]))
        print(f"  notes: {len(MATERIAL_NOTES)} materials")

        conn.commit()
    print(f"\nseeded {len(FAMILIES)} families, {len(PRECEDENTS)} precedents, "
          f"{len(MATERIAL_NOTES)} material notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
