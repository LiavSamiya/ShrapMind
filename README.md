# Fragment-to-Catalyst — catalyst selection engine

Takes a characterised fragment and returns the enzyme that degrades it, the
evidence behind that choice, and the specific ways the natural enzyme does not
fit body conditions.

Built for Nucleate Israel BioBattle 2026, MAFAT track — *Management of Retained
Shrapnel in High-Risk Anatomical Locations*.

> Research prototype. Not a medical device, not a clinical decision aid, and
> not validated for use in or on a person.

## What it does

```
fragment  →  retrieval  →  evidence-weighted ranking  →  enzyme + gap report
                                                      →  product burden bound
```

Input is a fragment of a known material in deep skeletal muscle. Output is one
selected catalyst with its UniProt accession, EC number, Rhea reaction, the
conditions its activity was actually measured under, and the publications that
report it — plus ranked alternatives and the brief for the engineering layer.

## Quick start

```bash
python -m f2c.cli build                 # pull PAZy, enrich from UniProtKB
python -m f2c.cli stats
python -m f2c.cli select --material PET --mass-mg 50 --crystallinity 35
python -m f2c.cli select --material PET --mass-mg 50 --json
python -m pytest tests/ -q
python tools/verify_sources.py --sample 40
```

No third-party runtime dependencies; `pytest` only for the tests.

## Data sources

| Source | Role | What it contributes |
|---|---|---|
| [PAZy](https://www.pazy.eu/) | seed, gold labels | enzymes whose activity on a given polymer was demonstrated in the lab, with the paper attached |
| [UniProtKB](https://www.uniprot.org/) | enrichment | review status, EC, Rhea/ChEBI reaction keys, curated optima, each carrying its PubMed id |
| [BRENDA](https://www.brenda-enzymes.org/) 2026.1 | kinetics | kcat, Km, optima — every value with the assay conditions it was measured under (CC BY 4.0) |

As built: **505** experimentally verified enzymes across 10 polymers; 235 carry
a UniProt accession, 167 are Swiss-Prot reviewed, 60 have an experimental
structure. BRENDA contributes **338 measurements** across 32 of them, which
lifts temperature-optimum coverage from 12 enzymes to 31 and pH from 17 to 32.

That is still 31 out of 505. The engine reports the scarcity rather than
papering over it.

Downloaded and mapped, not yet wired in: CAZy (cellulose families), M-CSA
(catalytic mechanism), InterPro, PDB, AlphaFold, ChEBI. Not reachable from a
script: SABIO-RK (serves its web app, not data) and FireProtDB (documented API
paths 404).

### A note on trusting curated databases

BRENDA is carefully curated and still ships citations that point at the wrong
paper. In release 2026.1, EC 3.1.1.101 attributes

> *Structural insight into molecular mechanism of poly(ethylene terephthalate)
> degradation* (2018)

to **PMID 2937183**, which is really a 1986 Russian paper on paediatric oral
surgery. Imported unchecked, that becomes a citation in a slide deck that
collapses the moment anyone clicks it.

`f2c/sources/brenda.py::suspect_references` drops references whose PMID cannot
be right for the stated year, and `tools/verify_sources.py --brenda-titles`
resolves each remaining id and compares titles. Existence alone is not enough:
a real PMID attached to the wrong paper looks perfect until someone opens it.

## The rules this engine will not break

These are enforced in code and covered by tests, because each one is a way a
plausible-looking answer turns out to be fiction.

1. **No number without its source.** Every measured value is an `Observation`
   carrying the database, the retrieval date and the PubMed id. There is no
   path for an unsourced constant to reach the output.
2. **Unknown is neutral, never good.** An unmeasured signal contributes a
   neutral prior at full weight. An early version scored only over the signals
   that happened to be present, which handed a perfect score to the enzyme
   nobody had characterised; `test_unmeasured_enzyme_cannot_outrank_a_measured_good_fit`
   locks that shut.
3. **Two different kinds of "no".** *No pathway* (glass, metal — no bond an
   enzyme can turn over) is a claim about chemistry. *No verified enzyme* (PE,
   PP) is a claim about evidence. Both are reported, never merged.
4. **Oligomer activity is not polymer activity.** Entries demonstrated only on
   soluble oligomers are excluded when the fragment is solid.
5. **No measurement is averaged across conditions.** Each stays a separate row
   with its own pH, temperature and substrate.
6. **Capacity is derived, rate is refused.** Complete degradation of a known
   mass releases a known molar quantity — a bound that needs no kinetic
   assumption. A release *schedule* would need turnover data on a solid
   fragment under serum, which does not exist publicly, so none is printed.

## What the ranking is, and is not

It ranks strength of experimental evidence and fit to body conditions:
replication across independent papers (0.30), temperature fit to 37 °C (0.25),
pH fit to 7.4 (0.20), Swiss-Prot curation (0.15), experimental structure (0.10).

It is **not** a predicted degradation rate. No public dataset links a sequence
to turnover on a solid fragment in tissue, so the engine does not pretend to
one. Closing that gap is what the lab loop is for.

## Worked example

`--material PET --mass-mg 50 --crystallinity 35` selects **TfH**
(*Thermobifida sp.*, Q6A0I4, EC 3.1.1.74), score 0.93, no unknown signals:

```
+ activity reported in 15 independent publications
+ temperature optimum median 37.5 C over 4 measurements (range 30) vs body 37 C
+ pH optimum median 8 over 3 measurements (range 2) vs body 7.4
+ Swiss-Prot reviewed entry
+ experimental structure available (4CG1)
```

Read the parenthesis before the median. **Range 30** means the four labs that
measured this enzyme's temperature optimum disagree across thirty degrees. The
median of 37.5 °C looks like a perfect match for body temperature and is in
fact the midpoint of a real disagreement. Reporting one without the other would
be the single most flattering lie this engine could tell, so it reports both.

Mass balance adds the hard part that needs no kinetics: 50 mg of PET releases
0.26 mmol of monomer at complete degradation, which is the capture capacity the
carrier must have. The release *schedule* is not reported, because nothing in
the public record measures turnover on a solid fragment under serum.

## Layout

```
f2c/
  schema.py      canonical entities; Observation binds value to evidence
  sources/       pazy.py (seed), uniprot.py (enrichment)
  warehouse.py   build, persist, load, describe
  retrieve.py    material → candidates; the two kinds of "no"
  rank.py        weighted scoring with explicit unknowns
  formulate.py   mass-balance product burden and capture capacity
  engine.py      orchestration → Decision
  report.py      human-readable rendering
  cli.py
tools/
  verify_sources.py   resolves every PMID, DOI and accession
tests/
```

## Verifying the citations

`tools/verify_sources.py` resolves every identifier against the issuing
authority: UniProt for accessions, NCBI esummary for PMIDs, and **Crossref**
for DOIs. DOIs are deliberately not checked through `doi.org`, which redirects
to publishers that return 403 to scripts — indistinguishable, from the outside,
from a DOI that was never registered.
