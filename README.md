# ShrapMind

**Fragment-to-Catalyst** — a catalyst selection engine for retained shrapnel.

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
python -m pytest tests/ -q              # 31 tests, no network needed
python -m f2c.cli stats
python -m f2c.cli select --material PET --mass-mg 50 --crystallinity 55 \
                         --particle-size-mm 0.8
python -m f2c.cli select --material PET --mass-mg 50 --json
```

The committed warehouse is enough to run all of that offline. To rebuild it
from the sources, or to check its citations:

```bash
python -m f2c.cli build                 # pull PAZy, enrich from UniProtKB
python tools/fetch_sources.py           # everything reachable without a login
python tools/verify_sources.py --sample 40
```

No third-party runtime dependencies; `pytest` only for the tests.

## The interface

Two self-contained pages, for the clinician or researcher who would use this
daily rather than read the source:

```bash
python -m f2c.cli export-ui             # Decisions for all 23 materials → JSON
python tools/build_ui.py                # → ui/fragment-to-catalyst.html
python tools/build_structure.py         # → ui/structure-built.html
```

Then open either file in a browser. There is no server and no build step beyond
those commands: each page carries its own data, so it works from a file:// URL
and can be sent to someone as a single attachment.

`fragment-to-catalyst.html` takes the fragment's material, mass, crystallinity
and particle size, and shows the selected enzyme with every measurement plotted
on a scale against body conditions — so a reader sees the spread, not just the
median — followed by the gaps, the fragment's own barriers, the product burden
from mass balance, and the downstream stages with the evidence class of each.

`structure-built.html` renders PDB 4CG1 with the catalytic triad highlighted.
That entry is 259 of 261 residues identical to Q6A0I4, the selected enzyme —
two substitutions, S18R and T136S — so the page says it is that close rather
than claiming it is the enzyme. The build re-derives the triad positions from
the coordinate file every time and refuses to produce a page if they are not
serine, aspartate and histidine, because UniProt numbers the precursor and the
PDB entry numbers the mature protein, forty residues apart.

## Data sources

| Source | Role | What it contributes |
|---|---|---|
| [PAZy](https://www.pazy.eu/) | seed, gold labels | enzymes whose activity on a given polymer was demonstrated in the lab, with the paper attached |
| [UniProtKB](https://www.uniprot.org/) | enrichment | review status, EC, Rhea/ChEBI reaction keys, curated optima, each carrying its PubMed id |
| [BRENDA](https://www.brenda-enzymes.org/) 2026.1 | kinetics | kcat, Km, optima — every value with the assay conditions it was measured under (CC BY 4.0) |

As built: **505** experimentally verified enzymes across 10 polymers; 235 carry
a UniProt accession, 167 are Swiss-Prot reviewed, 60 have an experimental
structure. BRENDA contributes **332 measurements** across 32 of them, which
lifts temperature-optimum coverage from 14 enzymes to 33 and pH from 17 to 30.

That is still 33 out of 505. The engine reports the scarcity rather than
papering over it.

Of those measurements, **289 are catalytic constants, and not one was measured
on the solid polymer**: 180 used a chromogenic model ester, 47 a soluble
oligomer, and 62 record no substrate at all. Every kcat and Km this project can
reach therefore describes activity on a dissolved stand-in. That is the single
most important thing the warehouse has to say, so the engine says it on every
candidate instead of letting the numbers imply otherwise.

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

Checking all 1,024 references in the EC entries this project uses found **three**
that point at a different paper. The cheap heuristic in
`f2c/sources/brenda.py::suspect_references` — a PMID too small for its stated
year — caught two of them. The third, PMID 18355276, is eight digits and
plausibly dated, and only resolving it and comparing titles revealed it belongs
to a different paper entirely.

So verification writes its findings to `data/raw/brenda/bad_references.json`,
and the importer reads that file back. A measurement whose every reference was
discredited is dropped rather than imported without a citation: otherwise a
number we know we cannot stand behind would enter the warehouse merely looking
uncited. That costs two enzymes their pH optimum, which is the right trade.

```bash
python tools/verify_sources.py --brenda-titles data/raw/brenda/subset.json
```

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
replication across independent papers (0.26), temperature fit to 37 °C (0.22),
pH fit to 7.4 (0.17), what the catalysis was measured on (0.17), Swiss-Prot
curation (0.10), experimental structure (0.08).

Two properties of that scoring matter more than the numbers:

**Every weight is spent on every candidate.** A signal nobody measured
contributes a neutral 0.5, not nothing. Scoring only the signals that happen to
be present rewards ignorance — an enzyme with no data would score a perfect
1.00 on the one thing known about it.

**A median is discounted by how much the labs disagree.** Four groups measured
TfH's temperature optimum at 25, 25, 50 and 55 °C. The median is 37.5 °C, which
looks like a flawless match for body temperature and is in fact the midpoint of
a thirty-degree disagreement. The spread shrinks the credit and raises a gap of
its own.

It is **not** a predicted degradation rate. No public dataset links a sequence
to turnover on a solid fragment in tissue, so the engine does not pretend to
one. Closing that gap is what the lab loop is for.

## Worked example

`--material PET --mass-mg 50 --crystallinity 55 --particle-size-mm 0.8`
selects **TfH** (*Thermobifida sp.*, Q6A0I4, EC 3.1.1.74), score 0.78, no
unknown signals:

```
+ activity reported in 15 independent publications
+ temperature optimum median 37.5 C over 4 measurements (range 30) vs body 37 C
+ temperature measurements disagree across 30 C, so the median is discounted
+ pH optimum median 8 over 3 measurements (range 2) vs body 7.4
+ pH measurements disagree across 2 units, so the median is discounted
+ 7 catalytic constants measured on 4x a chromogenic model substrate,
  3x an unrecorded substrate
+ Swiss-Prot reviewed entry
+ experimental structure available (4CG1)
```

Read the parenthesis before the median, and the substrate before the constant.
Four labs disagree across thirty degrees; the midpoint is not an optimum. Seven
catalytic constants exist and none of them touched a solid; they prove the
protein is a live hydrolase, which is worth knowing and is not the same claim.

The selection then carries a brief for the lab — the gaps it would take to make
this enzyme usable, each with a target and an action:

```
* temperature spread : 4 publications disagree across 30 C (25, 25, 50, 55 C)
                       -> one assay at 37 C under comparable conditions
* ph                 : optimum pH 8 is 0.6 units from body pH
                       -> re-tune the active-site electrostatics for neutral pH
* catalytic evidence : no constant was measured on the polymer
                       -> kcat and Km against the solid polymer at 37 C in serum
```

And separately, the barriers that belong to the fragment rather than the
catalyst, which choosing a different enzyme would not remove:

```
surface area : 271.74 mm2 (5.435 mm2/mg), cubes of 0.8 mm filling the volume
crystallinity: 55% crystalline sets a ceiling on how much can be degraded,
               and the enzyme's constants come from soluble substrates where
               crystallinity does not apply, so they say nothing about it
surface state: in tissue the enzyme meets adsorbed plasma protein, soil and
               blood before it meets the polymer
```

Mass balance adds the hard part that needs no kinetics: 50 mg of PET releases
0.26 mmol of monomer at complete degradation, which is the capture capacity the
carrier must have. The release *schedule* is not reported, because nothing in
the public record measures turnover on a solid fragment under serum.

## Layout

```
f2c/
  schema.py      canonical entities; Observation binds value to evidence
  sources/       pazy.py (seed), uniprot.py, brenda.py (kinetics)
  warehouse.py   build, persist, load, describe
  retrieve.py    material → candidates; the two kinds of "no"
  substrate.py   what a catalytic constant was actually measured on
  rank.py        weighted scoring with explicit unknowns
  formulate.py   mass balance, fragment geometry, accessibility barriers
  pipeline.py    the stages after selection, each with its evidence class
  engine.py      orchestration → Decision
  report.py      human-readable rendering
  export_ui.py   the same Decisions as JSON for the browser
  cli.py
ui/
  index.html         the interface; reads an inlined dataset
  structure.html     3Dmol viewer; reads inlined coordinates
tools/
  fetch_sources.py    downloads what is reachable, names what is not
  verify_sources.py   resolves every PMID, DOI and accession
  build_ui.py         inlines the dataset into a single file
  build_structure.py  fetches 4CG1 and verifies the triad numbering
data/
  warehouse.json      the committed slice the engine runs on
tests/
```

## Verifying the citations

`tools/verify_sources.py` resolves every identifier against the issuing
authority: UniProt for accessions, NCBI esummary for PMIDs, and **Crossref**
for DOIs. DOIs are deliberately not checked through `doi.org`, which redirects
to publishers that return 403 to scripts — indistinguishable, from the outside,
from a DOI that was never registered.
