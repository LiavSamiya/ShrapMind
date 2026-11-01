# ShrapMind — the Fragment-to-Catalyst engine

**A design-and-simulation loop that works out what a retained fragment is made of,
searches for an enzyme candidate that could erode *that specific material* inside a
product-capturing hydrogel, and refuses to recommend anything that fails a safety
gate.**

> ### Read this first
>
> ShrapMind is a **research simulation tool**. It models material chemistry using a
> parametric kinetic model fitted to published data. It is **not** molecular dynamics,
> **not** a protein-structure predictor, and **not** a medical device.
>
> Every candidate it produces is a **simulation hypothesis requiring wet-lab
> validation**. The system does not provide dosing, indications, eligibility
> judgements or treatment protocols, and a hard gate in `shared/safety.py` **refuses**
> to generate them — the design loop halts rather than answering.
>
> Nothing here has been validated in vitro, in vivo or clinically.

Built for BioBattle 2026. Architecture ported from
[VooDo](https://github.com/VooDo-AI/VooDo), winner of HackAgents BIU 2026.

---

## The problem

A patient has a fragment — wood, polymer, metal — retained in soft tissue. It hurts,
it impairs function, and the only two options are both bad: cut it out, risking
iatrogenic damage to nerves and vessels in a crowded compartment, or leave it and
watch a fibrotic capsule tighten around it for years.

Literature review puts 50–70% of penetrating fragments in the upper and lower limbs,
most at 1–6 cm depth — shallow enough to reach with an ultrasound-guided needle. That
is the opening: **a middle option between watchful waiting and the knife.**

ShrapMind is the computational half of that idea. It does not inject anything. It
answers a narrower, tractable question: *given this material, is there an enzyme
candidate whose simulated behaviour inside a capturing hydrogel is worth taking to a
wet lab — and which measurement should we make first?*

| Problem | How ShrapMind addresses it |
|---|---|
| Fragment material varies per case, and "metal" or "plastic" is not a specification | A **fragment passport** with an explicit confidence score. Confidence 0 is a valid output meaning *identify it before designing anything* |
| A high `k_cat` from a paper says little about 37 °C in serum | Every kinetic record carries **the conditions it was measured under**, and the agent is required to carry that caveat into its report |
| Partial degradation could create mobile microparticles — worse than leaving the fragment whole | A **fragmentation gate** on the simulated particle fraction, and a surface-erosion model rather than a bulk-scission one |
| The reaction creates products inside tissue | A closed **mass balance** plus capture and free-product gates. For the metal route, capture — not rate — is the binding constraint |
| Literature precedent gets oversold in pitches | The precedent table stores **what each paper does not prove**, and the report must repeat it |
| A model asked for a dose will produce one | A **clinical-output gate** that halts the run instead of answering |

---

## What makes it a system rather than a lookup table

**The gates are not advisory.** `run_safety_gates` runs ten checks — mass balance,
fragmentation, free product, capture efficiency, forbidden products, predictive
confidence, meaningful erosion, tissue off-target, anatomical tier, material
identification — and each reports *the number that decided it*. A failure **halts the
loop**. The agent cannot rephrase past it, the ranking never puts a failing candidate
above a passing one, and the approval endpoint refuses to promote one. A gate you can
argue with is not a gate.

**Uncertainty is the product, not a caveat.** The assay returns a 5–95 percentile band
over sampled kinetic parameters, because published constants for the same enzyme vary
by an order of magnitude. If the band spans an order of magnitude, the finding is *"we
need this measurement"* — and `plan_next_experiment` ranks experiments by exactly that:
uncertainty × plausible upside. Measuring a candidate that is confidently bad teaches
you nothing.

**A no-go is a result.** Seven materials are marked no-go with reasons
(polyethylene, polypropylene, polystyrene, glass, lead, copper, aluminium). The agent
reports that rather than substituting a weaker candidate to have something to show.

**Scores are auditable, not learned.** `predict_properties` is an additive heuristic
over a documented edit catalogue and returns its per-edit contributions. It says so in
its own output. A trained black box would score better and justify less.

---

## Architecture

Four deployment units sharing one wire-protocol package.

```
  browser ──/ws──► FastAPI (server/app/main.py)
                     │  asyncio.Queue ◄── emit() from the worker thread
                     ▼
                run_design()  (server/agent/agent.py — synchronous, in to_thread)
                     │  dispatch() ──► Bench ──► bridge.call_sync()
                     ▼                              │
                LLMClient                     /worker WS ◄── dials out
                     │                                      simulation worker
                server/db/client.py (Postgres + pgvector)   (client/worker/)
                                                             engines.py
                                                             kinetics.py
```

**The worker dials out.** The backend never connects inward, so the machine with the
compute — a GPU box, a lab workstation, a laptop behind NAT — needs no inbound port and
no VPN. One backend can fan work to several workers keyed by `client_id`.

**The agent loop is synchronous.** A step-by-step loop with explicit guards is easier
to reason about and to argue with in review than an async one. `asyncio.to_thread` plus
a thread-safe `emit` shim is the only seam between it and the live UI.

**History is rebuilt every turn.** The model never receives a growing transcript of its
own tool calls. It gets the case, a plain-text log of what was attempted, and the
**current bench state** serialized fresh. Given a transcript of its own actions a model
assumes they succeeded; given current state it has to look.

**Guardrails are pushback, not failure.** Nearly every guard appends a coaching line to
the action log and continues. The two exceptions — a gate failure and a clinical-output
refusal — break the loop immediately.

### The ten stages

```
INSPECT      read_passport
CHARACTERIZE characterize_fragment    → material family + confidence
REACTION     define_reaction          → bond class, products, FORBIDDEN products
             get_material_notes       → what the real rate limit is
RETRIEVE     retrieve_enzymes         → families, filtered by material
             retrieve_precedents      → and what they do NOT prove
GENERATE     propose_variants         → sequence-level proposals
PREDICT      predict_properties       → auditable developability scores
             score_kinetics           → cheap shortlisting
SIMULATE     simulate_hydrogel_assay  → the virtual experiment, with a band
             check_mass_balance       → did the books close?
GATE         run_safety_gates         → MANDATORY. A failure ends the run.
RANK         rank_candidates          → multi-objective, gates first
             plan_next_experiment     → what to measure in the wet lab
REPORT       submit_candidate         → queue for human review
             finish                   → the report
```

### Two modes

- **Run** — executes the pipeline: retrieval, simulation, gates, ranking, report.
- **Explain** — walks the same pipeline on the same case and teaches each stage.
  Simulation and write tools are **withheld from the schema**, not offered and then
  refused, and a simulation call is rewritten into a `highlight_step` annotation.

### The simulation

`client/worker/kinetics.py` integrates four coupled pools with RK4 and closes mass
balance to ~1e-16:

```
fragment ──► free products ──► gel-captured ──► cleared
         └──► particles (the fragmentation gate watches this)
```

Rate is proportional to *accessible surface area*, which shrinks as the fragment does
(shrinking-core). Modulated by Arrhenius temperature rise × a Gaussian denaturation
envelope, a pH envelope, Ogston mesh hindrance on both enzyme and product, serum
protein fouling, and exponential enzyme inactivation. The mesh term is what makes the
gel a selective filter: small products diffuse out, microparticles do not.

### Approval is the write chokepoint

Nothing reaches `validated_library` on the hot path. The agent and the dashboard both
call `submit_pending_candidate`, which sanitizes every text field in one place; only
`approve_pending_candidate` promotes a row, computing the embedding at approval time —
and it **refuses** a candidate whose gates did not pass.

Approving means *"this is a hypothesis worth a wet-lab experiment."* It does not mean
validated, safe, or clinically usable, and the dashboard says so on screen.

---

## Repo layout

| Path | Runs on | Purpose |
|---|---|---|
| [`shared/`](shared/) | both | Wire types, config, safety. Source of truth for the tool vocabulary |
| [`shared/safety.py`](shared/safety.py) | both | Four fail-closed layers, including the clinical-output gate |
| [`server/agent/`](server/agent/) | backend | The design loop, LLM client, tool registry, per-material notes |
| [`server/app/`](server/app/) | backend | FastAPI, the console, the reviewer dashboard, the reverse-WS bridge |
| [`server/db/`](server/db/) | backend | Postgres + pgvector, seed data, approval workflow |
| [`client/worker/`](client/worker/) | GPU / lab box | Thin dial-out client: the engines and the kinetic model |
| [`tests/`](tests/) | dev | 53 tests, including both hard stops |

---

## Quickstart

### Fastest path — no API key, no database, no dataset

```bash
pip install -r server/app/requirements.txt -r client/worker/requirements.txt
```

```bash
cp .env.example .env
```

```bash
MOCK_LLM=1 SKIP_DB=1 PYTHONPATH=. python -m uvicorn server.app.main:app --port 7860
```

If you left `WORKER_TOKEN` empty, the backend mints one at startup and prints it:

```
[config] WORKER_TOKEN not set - minted a dev token: f3c970e34549b07d...
```

Paste that into a second terminal (or set `WORKER_TOKEN` in `.env` to skip this step):

```bash
PYTHONPATH=. python -m client.worker.main --backend ws://localhost:7860 --token <the-printed-token>
```

Open <http://localhost:7860>. The scripted run walks all ten stages with the **real**
simulator — only the LLM is mocked.

To exercise the console with no worker at all, use `MOCK_AGENT=1` instead.

### Full stack

```bash
cp .env.example .env
```

Fill in `WORKER_TOKEN`, `POSTGRES_PASSWORD`, `REVIEWER_PASSWORD`, `ADMIN_PASSWORD` and
an LLM key, then:

```bash
./server/scripts/dev_all.sh
```

That brings up Postgres + pgvector and the backend, waits for `/health`, and seeds the
knowledge base only if it is empty. Start the worker as above.

- console — <http://localhost:7860/>
- reviewer — <http://localhost:7860/review>
- health — <http://localhost:7860/health>

### Standalone, no web UI

```bash
PYTHONPATH=. python -m server.agent.agent --case "wood splinter in forearm" --mock-llm --skip-db
```

### Tests and lint

```bash
python -m pytest tests/ -q
```

```bash
ruff check .
```

---

## Configuration

Any OpenAI-compatible endpoint works — set `LLM_MODEL` and `LLM_BASE_URL`. Leave
`LLM_BASE_URL` empty to use OpenRouter; a Gemini model id with `GEMINI_API_KEY` routes
to Google's compat endpoint automatically.

Set `SHRAPMIND_PROD=1` in deployment. It refuses to boot on a missing LLM key, a short
`WORKER_TOKEN` or a weak dashboard password, and it force-disables `MOCK_LLM`,
`MOCK_AGENT` and `SKIP_DB` so a stray env var cannot quietly downgrade a deploy to the
scripted demo.

Every tool call is written to a one-line-per-call JSON audit log
(`~/.shrapmind/audit.log` by default) with control characters scrubbed, so a tool
argument cannot forge a log line.

---

## Limits, stated plainly

- **The simulator is parametric.** It predicts what a given set of kinetic parameters
  implies under given conditions. It does not predict whether a designed sequence
  folds, expresses, or binds — nothing here is structurally modelled.
- **`propose_variants` is an enumeration**, not a generative model. It proposes
  sequence-level edits from a documented catalogue with directional effects.
- **Seed kinetics are order-of-magnitude placeholders** drawn from the cited
  literature. The `enzyme_families` table is shaped to receive a real BRENDA import;
  `scripts/ingest_brenda.py` is the natural next task.
- **Material identification is the weakest link.** The spectral heuristics in
  `characterize_fragment` are coarse and documented as such; real deployment needs a
  spectral library match. The system is built to say "confidence 0, go get a sample."
- **The metal route is not near-term.** It is seeded, gated and reported as research —
  slow, oxygen- and passivation-limited, and constrained by ion capture rather than
  rate.
- **Nothing has been validated.** No wet-lab work, no animal model, no clinical data.

---

## Team

BioBattle 2026 — L. Samia · A. Nini Barak · Y. Shenhav · T. Tzadikevich · N. Talor

Mentorship on clinical framing and the imaging trade-off: Dr. Noa (field-hospital
fragment-injury care; Weizmann Institute).

## License

MIT — see [LICENSE](LICENSE).
