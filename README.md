# ShrapMind — Fragment-to-Catalyst

**An evidence engine and simulator for retained fragments: what is this fragment made
of, is there a curated enzyme that could erode *that* material, and does the evidence
actually support saying so?**

Built for Nucleate Israel BioBattle 2026, MAFAT track — *Management of Retained
Shrapnel in High-Risk Anatomical Locations*. Architecture ported from
[VooDo](https://github.com/VooDo-AI/VooDo), winner of HackAgents BIU 2026.

> ### Read this first
>
> **Research prototype. Not a medical device, not a clinical decision aid, and not
> validated for use in or on a person.**
>
> The simulator is a parametric kinetic model, not molecular dynamics and not a
> structure predictor. Every output is a hypothesis requiring wet-lab validation. The
> system does not provide dosing, indications or treatment protocols, and a hard gate
> in `shared/safety.py` **refuses** to generate them — the design loop halts rather
> than answering.

---

## The honest headline

This system's most important output is a refusal, and it is worth stating plainly
before anything else:

**No turnover number in the knowledge base was ever measured on a solid fragment.**

Of 289 kinetic measurements across 505 experimentally-verified enzymes, 168 were made
on chromogenic model esters (4-nitrophenyl acetate and relatives), 42 on soluble
oligomers, 58 record no substrate at all, and **none** on the real material. Only 8 of
the 505 enzymes have a `k_cat` at all. **None** has a measured half-life. One of the
eight is Proteinase K at 3509 s⁻¹ — measured on *casein*, milk protein. Fed naively
into a surface-erosion model, that single number predicts spectacular PLA degradation.

So most runs end in a reasoned no-go, naming the substrate each constant was actually
measured on and citing the paper. That is the finding, not a fault. A system that
turned these constants into confident µm/day figures would be more impressive and
less true.

---

## What it does

```
fragment  →  characterise  →  retrieve curated evidence  →  simulate in hydrogel
                                                         →  14 safety gates
                                                         →  rank, or refuse
                                                         →  what to measure next
```

### Two halves, joined

| | |
|---|---|
| **`f2c/` — the evidence layer** | 505 experimentally-verified plastic-degrading enzymes from PAZy, enriched from UniProtKB and BRENDA 2026.1. 420 condition-bearing observations, **a citation on every number**, measurement-level so assays at different pH are never collapsed. Plus its own retrieval-and-ranking engine and CLI. |
| **`server/` + `client/` — the architecture** | Streaming agent loop, surface-erosion simulator with uncertainty bands, the gate battery, approval workflow, console. |

The join is `server/db/evidence.py`, and its whole job is to stop a number crossing
without its provenance.

### The rules that do the work

Both halves share one design rule, taken from f2c because it is the stricter one:

> *A number never travels without its evidence. `None` means "not measured", which is
> different from "measured and found to be zero".*

Concretely:

- **Provenance bounds the claim.** f2c's `substrate.classify()` is carried through to
  the simulation, taking the **weakest** class across the constants used — f2c scores
  on the strongest evidence available, but a simulation must be judged on its weakest
  input, because that is what bounds the result.
- **Provenance sets the uncertainty.** `polymer` 0.25 · `oligomer` 0.50 · `model` 0.90
  · `unknown` 1.20. A model-ester-derived rate comes back spanning roughly an order of
  magnitude, which trips the confidence gate *unaided* — no special case needed.
- **Nothing is silently defaulted.** A missing `k_cat`, `K_m` or half-life is reported
  in `assumed_parameters` and fails a gate. A quietly substituted default is how a
  simulation starts lying: the number looks identical whether it came from a paper or
  from a fallback dict.
- **Three kinds of "no" stay distinct.** *No enzymatic route* (glass, lead, titanium —
  f2c's list) · *no documented route* (polyethylene: absent evidence, **not** proof of
  impossibility) · *not identified yet* (characterise first). Collapsing them would let
  "nobody has looked" masquerade as "it cannot work".
- **Coverage is stated, not implied.** Ten polymers are curated. Cellulose and cotton
  return an explicit empty naming what *is* covered, rather than a plausible
  placeholder.

### The 14 gates

Mass balance · fragmentation · free product · capture efficiency · forbidden products ·
product characterised · hazard resolved · predictive confidence · meaningful erosion ·
tissue off-target · anatomical tier · material identified · **kinetics provenance** ·
**measured inputs**

Each reports *the number that decided it*. A failure ends the **recommendation**, not
the run: the loop locks into report-only mode where simulating, gating and submitting
are blocked, but ranking, experiment planning and `finish(success=false)` remain —
because "the measurement everyone needs has never been made" is the most useful thing
this system can say, and halting outright would throw away the write-up.

`hazard_resolved` fails in the committed state **by design**: GHS codes are regulatory
strings that must be fetched, never hand-entered. A gate firing on a half-remembered
hazard code would be worse than no data. It clears when `tools/fetch_chemistry.py` can
reach PubChem.

### The chemistry layer

The simulator's physics depended on compound properties nothing sourced — nine
hand-written molecular radii were setting the mesh-hindrance term and, through it, the
capture gate. Now (`f2c/sources/chemistry.py`), three tiers, and the tier travels with
the value:

| tier | meaning |
|---|---|
| `resolved` | fetched live from PubChem or ChEBI |
| `derived` | **computed here** — molecular weight from atomic masses, radius from a cited correlation with a stated validity floor |
| `reference` | the molecular **formula** only, hand-entered as chemical identity and tied to its ChEBI id |

Hazard is **never** hand-entered. The difference is visible in the physics: ethylene
glycol (r = 0.26 nm, derived from C₂H₆O₂) escapes the gel to 43% capture where
cellobiose (r = 0.51 nm) holds at 58% — which is exactly why the material notes flag
ethylene glycol as the product to bound on the polyester route.

---

## Quickstart

### No API key, no database, no dataset beyond what is committed

```bash
pip install -r server/app/requirements.txt -r client/worker/requirements.txt
```

```bash
cp .env.example .env
```

```bash
MOCK_LLM=1 SKIP_DB=1 PYTHONPATH=. python -m uvicorn server.app.main:app --port 7860
```

The backend prints a dev worker token if you left `WORKER_TOKEN` empty. Paste it into
a second terminal:

```bash
PYTHONPATH=. python -m client.worker.main --backend ws://localhost:7860 --token <the-printed-token>
```

Open <http://localhost:7860>. The scripted run walks a **PET** case against the real
warehouse — only the LLM is mocked — and correctly ends in a no-go, citing
PMID:35557867 and naming 4-nitrophenyl butanoate as what the constant came from.

### f2c's own CLI still works

```bash
python -m f2c.cli select --material PET --mass-mg 50 --crystallinity 55
```

```bash
python -m f2c.cli stats
```

### Full stack

```bash
./server/scripts/dev_all.sh
```

Postgres + pgvector for semantic search at scale. **Not required** to get real
evidence — the warehouse is read directly, so `SKIP_DB=1` still runs on real data.

### Tests and lint

```bash
python -m pytest tests/ -q
```

109 tests: 31 f2c (unchanged) and 78 here, including that mass balance closes to
~1e-16 across a parameter sweep, that proxy kinetics are refused and the refusal names
the assay substrate, that molecular weights are computed rather than recalled, and
that both hard stops halt the loop.

```bash
ruff check .
```

`f2c/` and `tools/` are kept byte-for-byte as written and excluded from this project's
lint settings — their tests establish their correctness, and reformatting them would
be churn for no benefit.

---

## Refreshing the data

| source | how | current |
|---|---|---|
| PAZy | `python -m f2c.cli build` | live |
| UniProtKB | same, per-accession, disk-cached | live |
| BRENDA | **manual** — the licence box on brenda-enzymes.org must be ticked by a person | frozen at 2026.1 |
| ChEBI / PubChem | `python tools/fetch_chemistry.py` | **not yet resolved** |

`/health` and the console sidebar both report the snapshot date, what it covers, and
whether hazard has been resolved — because a recommendation read without knowing
whether the data is five days or five months old is a recommendation read wrong.

**Network.** The chemistry fetchers need `pubchem.ncbi.nlm.nih.gov` and
`www.ebi.ac.uk`. A restricted cloud environment denies both; add them under **Allowed
domains** in the environment's network settings. Offline, the fetchers are a no-op
that leave the snapshot untouched and exit non-zero rather than writing partial data.

---

## Repo layout

| Path | Purpose |
|---|---|
| [`f2c/`](f2c/) | The evidence layer: schema, warehouse, PAZy/UniProt/BRENDA sources, substrate classifier, and f2c's own engine |
| [`f2c/sources/chemistry.py`](f2c/sources/chemistry.py) | Compound identity, derived physics, GHS hazard |
| [`server/db/evidence.py`](server/db/evidence.py) | **The join.** Warehouse → simulator inputs, carrying provenance |
| [`server/agent/`](server/agent/) | The design loop, tool registry, per-material notes |
| [`server/app/`](server/app/) | FastAPI, console, reviewer dashboard, reverse-WS bridge |
| [`client/worker/`](client/worker/) | Dial-out worker: the engines and the kinetic model |
| [`data/`](data/) | The committed snapshots — warehouse, BRENDA subset, compounds |
| [`tools/`](tools/) | Fetch and verification scripts |

---

## Limits, stated plainly

- **The evidence covers plastics.** PAZy is a plastics-active enzyme database. Cellulose
  and cotton have **zero** curated enzymes here, so the wood route — which the concept
  brief leads with, on the sound argument that glucose and cellobiose are the mildest
  products of any material — carries no kinetic support in this system. The gap is
  reported, never filled with a constant borrowed from a polyester.
- **The metal route is contested, and both positions are shown.** f2c classes iron as
  non-enzymatic (redox corrosion, not hydrolysis). This project keeps it research-tier,
  gated on ion capture rather than rate, and reports f2c's objection alongside any
  result.
- **`propose_variants` is an enumeration**, not a generative model, over a documented
  edit catalogue with directional effects. No folding, expression or binding is
  predicted anywhere.
- **Developability scores are an additive heuristic** and say so in their own output,
  returning per-edit contributions so they can be audited rather than trusted.
- **Nothing has been validated.** No wet-lab work, no animal model, no clinical data.

---

## Team

L. Samia · A. Nini Barak · Y. Shenhav · T. Tzadikevich · N. Talor

Mentorship on clinical framing and the imaging trade-off: Dr. Noa (field-hospital
fragment-injury care; Weizmann Institute).

## License

MIT — see [LICENSE](LICENSE). PAZy, UniProtKB, BRENDA (CC BY 4.0), ChEBI and PubChem
each ask to be cited; see `data/raw/manifest.json` for provenance.
