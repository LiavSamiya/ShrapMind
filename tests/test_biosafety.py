"""Will the enzyme, or what it releases, attack the patient?

These are the tests for the question the gate battery originally failed to
ask: not "is the target bond present in tissue" but "what else can this
particular protein do".
"""
import pytest

from shared.biosafety import (
    assess_enzyme,
    assess_products,
    organism_flags,
)

# ---------------------------------------------------------------- the enzyme


@pytest.mark.parametrize("ec,name", [
    ("3.4.21.64", "Proteinase K"),
    ("3.4.21.62", "Subtilisin Carlsberg"),
    ("3.4.-.-", "PAM"),
    ("3.4.24.7", "interstitial collagenase"),
])
def test_peptidases_are_blocked(ec, name):
    """Peptide bonds are what human structural protein is made of."""
    s = assess_enzyme(name, [ec])
    assert s.blocking
    assert any(r.kind == "proteolysis" for r in s.risks)


def test_the_block_names_the_host_substrate_at_risk():
    """A refusal has to carry its reason, or a reviewer cannot disagree with
    it."""
    s = assess_enzyme("Proteinase K", ["3.4.21.64"])
    risk = next(r for r in s.risks if r.severity == "blocking")
    assert "collagen" in risk.why or "collagen" in risk.host_substrate
    assert risk.tier == "established"
    assert risk.basis


def test_a_protease_is_caught_by_name_when_the_ec_is_missing():
    """EC numbers in the warehouse are often partial or absent. A missing EC
    must not mean a missing flag - the warehouse contains an entry named only
    'protease' with no EC at all."""
    s = assess_enzyme("protease", [])
    assert s.blocking


@pytest.mark.parametrize("name", [
    "collagenase", "elastase", "hyaluronidase", "phospholipase A2",
    "bromelain", "keratinase",
])
def test_tissue_degrading_families_are_blocked_by_name(name):
    assert assess_enzyme(name, []).blocking


def test_hyaluronidase_is_blocked_for_defeating_containment():
    """It is used clinically as a spreading factor - the exact opposite of
    what a contained depot needs."""
    s = assess_enzyme("hyaluronidase", ["3.2.1.35"])
    assert s.blocking
    assert any("spreading" in r.why.lower() for r in s.risks)


def test_lipases_are_serious_but_not_blocking():
    """Host fat is a real substrate, but the consequence is local irritation
    rather than loss of structural integrity - the severities must differ or
    they carry no information."""
    s = assess_enzyme("a lipase", ["3.1.1.3"])
    assert not s.blocking
    assert s.worst == "serious"


def test_carboxylesterases_are_only_a_caution():
    """These are the main class in the warehouse. If they were blocking there
    would be nothing left, so the gate would be useless - the severity has to
    track the actual risk."""
    s = assess_enzyme("PETase", ["3.1.1.101"])
    assert not s.blocking
    assert s.worst in ("caution", "note")


def test_peroxidases_are_flagged_for_oxidative_stress():
    s = assess_enzyme("LiP", ["1.11.1.-"])
    assert any(r.kind == "oxidative" for r in s.risks)


def test_the_most_specific_ec_class_wins():
    """3.4.21 (serine endopeptidase) carries a more specific explanation than
    the generic 3.4, and the specific one should be reported."""
    s = assess_enzyme("Subtilisin", ["3.4.21.62"])
    risk = next(r for r in s.risks if r.kind == "proteolysis")
    assert risk.basis == "EC 3.4.21"


def test_a_clean_esterase_is_not_flagged_as_blocking():
    assert not assess_enzyme("IsPETase", ["3.1.1.101"]).blocking


def test_absence_of_a_flag_is_reported_as_absence_not_safety():
    """The wording matters: this system must never imply it has cleared an
    enzyme it has merely failed to flag.

    Note the example: a carboxylesterase like IsPETase DOES pick up a caution
    flag from EC 3.1.1, so an unflagged enzyme is one with no recognised
    class at all - which is itself the weakest possible position to be in.
    """
    s = assess_enzyme("Nyl84", [])
    assert s.risks == []
    assert "not evidence of selectivity" in s.summary()


# ---------------------------------------------------------------- organisms


def test_wound_pathogen_genera_are_flagged():
    assert organism_flags("Clostridium botulinum")
    assert organism_flags("Pseudomonas aeruginosa")


def test_candidatus_is_not_mistaken_for_candida():
    """'Candidatus' is a taxonomic prefix meaning 'candidate taxon'. Flagging
    an uncultured archaeon as a fungal pathogen would discredit every other
    flag this module raises - and the warehouse contains several."""
    assert organism_flags("Candidatus Bathyarchaeota archaeon") == []
    assert organism_flags("Candida albicans")


def test_genus_only_names_do_not_match_a_species_specific_flag():
    """The flag is on Pseudomonas aeruginosa specifically, not on every
    Pseudomonas - the warehouse has eleven 'Pseudomonas sp.' entries."""
    assert organism_flags("Pseudomonas sp.") == []


def test_benign_organisms_are_not_flagged():
    for org in ("Thermobifida fusca", "Compost metagenome", "Cupriavidus necator"):
        assert organism_flags(org) == []


# ---------------------------------------------------------------- products


def test_free_iron_is_blocked_on_fenton_chemistry():
    """The mechanistic reason the metal route is bounded by capture and not by
    rate: a wound already contains the peroxide co-reactant."""
    a = assess_products(["fe_ion"])
    assert "fe_ion" in a["blocking"]
    h = next(x for x in a["hazards"] if x["product"] == "fe_ion")
    assert "Fenton" in h["mechanism"]
    assert "hydroxyl radical" in h["mechanism"]
    assert "chelation" in h["requires"].lower()


def test_bisphenol_a_blocks_the_polycarbonate_route():
    assert "bisphenol_a" in assess_products(["bisphenol_a", "carbonate"])["blocking"]


def test_aromatic_amine_blocks_polyurethane():
    assert "aromatic_amine" in assess_products(["aromatic_amine"])["blocking"]


def test_particulate_is_blocked_as_worse_than_the_untreated_state():
    a = assess_products(["microparticle"])
    h = next(x for x in a["hazards"] if x["product"] == "microparticle")
    assert "worse than the untreated state" in h["requires"]


def test_ethylene_glycol_is_serious_with_its_metabolic_route_named():
    a = assess_products(["ethylene_glycol"])
    h = next(x for x in a["hazards"] if x["product"] == "ethylene_glycol")
    assert h["severity"] == "serious"
    assert "oxal" in h["mechanism"].lower()
    assert not a["blocking"]


def test_butanediol_carries_its_ghb_route():
    h = next(x for x in assess_products(["butanediol"])["hazards"]
             if x["product"] == "butanediol")
    assert "gamma-hydroxybutyrate" in h["mechanism"] or "GHB" in h["mechanism"]


def test_the_cellulose_product_panel_is_clean():
    """The reason the concept brief's wood-first argument stands on product
    safety even though the kinetic evidence does not exist."""
    a = assess_products(["cellobiose", "glucose"])
    assert a["blocking"] == []
    assert a["worst_severity"] == "note"
    assert len(a["benign"]) == 2


def test_an_unknown_product_is_reported_as_unassessed_not_safe():
    a = assess_products(["mystery_goo"])
    assert a["unassessed"] == ["mystery_goo"]
    assert "not assessed" in a["summary"]
