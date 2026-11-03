# ops

Not part of the product. This holds the one file the BioBattle team-page
automation depends on, because that file otherwise exists nowhere durable.

## drive-sync-prompt.txt

The scheduled task "Shrapnel · סנכרון דרייב" runs twice a day and reads its
instructions from `/home/user/shrapnel/sync-prompt.txt` — a path inside the
cloud container, not in any repository. Containers are reclaimed after a period
of inactivity, and a new one would not have that file, so the task would keep
firing and do nothing.

This is the copy of record. To restore the task after a container is replaced:

```bash
mkdir -p /home/user/shrapnel
cp ops/drive-sync-prompt.txt /home/user/shrapnel/sync-prompt.txt
```

Edit this copy, not the one under `/home/user/shrapnel/`, and copy it across —
otherwise the two drift and the restore quietly reverts a fix.

## The published pages

Nine artifacts were published for this project. Five are current; the other
four are earlier work, kept rather than deleted. The directory that lists all
nine lives in the `#index` section of `ui/app.html`, so it ships with the
engine rather than existing only as a message in a chat.

| Page | Artifact | Source in this repo |
|---|---|---|
| ShrapMind (entry point) | `XQgkTkYvMmCjTXCqcXUr9H` | `ui/app.html` → `tools/build_app.py` → `ui/shrapmind.html` |
| Fragment-to-Catalyst Safety Review | `9NDiDW7T9dgooUJEGD9jYt` | `ui/safety-review.src.html` → `tools/build_safety_review.py` → `ui/safety-review.html` |
| ביקורת ארכיטקטורת ההידרוג'ל | `7vSe3aYcf4KM8KQKTzbfD5` | `ui/carrier-review.html` |
| Ferroxidase Bench Protocol | `HeCKs9GsXQ4SqaZWYLhunm` | `ui/protocol.en.src.html` → `tools/build_protocol.py` |
| פרוטוקול פרוקסידאז | `5eHNCDQXRmxf82gyNiDsSg` | `ui/protocol.src.html` → `tools/build_protocol.py` |
| Shrapnel — team workspace | `R8WfMNJXNCrfk7jiMiAYMj` | not in this repo; holds its own live database written by the team |
| TfH Catalytic Site | `TmWMoL2bKvSPyrL63t9JVf` | superseded — its viewer is inline in `ui/app.html` |
| Shrapnel · רקע לבדיקה | `5c9UekC5TgCLZ15cQ5ueEn` | earlier work |
| מפת סיכון לרסיסים | `HPveDZ1o2N1QZhYgWbJhKR` | earlier work |
| פיץ׳ מפת סיכון לרסיסים | `UYLYujtA7eAyvUjKD7Er2P` | earlier work |

The safety review was written as an artifact and existed only as a published
page; it is checked in here for the same reason `tools/build_structure.py`
exists — a page that cannot be rebuilt from this repo is a page that is lost
when the container is reclaimed.

The team workspace is deliberately not folded into the entry point. Its
content is written by the team into a database keyed to its own URL, so
copying the page would strand the content.


## Keeping the pages honest

Three checkers, each for a different way a number goes wrong:

| Tool | Checks | The failure it was built after |
|---|---|---|
| `tools/verify_sources.py` | imported warehouse data | BRENDA shipped three wrong citations in release 2026.1 |
| `tools/verify_refs.py` | hand-typed references in `f2c/` | seven fabricated DOIs in the metal arm, including a ceruloplasmin citation pointing at a ferritin structure paper |
| `tools/verify_consistency.py` | figures the published pages state | the safety review kept stating its 2026-10-27 figures after the engine changed three times |

`verify_consistency` runs inside the test suite, so a page that contradicts the
engine fails `pytest` rather than waiting for somebody to notice. Its `claimed`
values are transcribed from the published pages by hand on purpose: editing a
page means editing the claim too, and editing only one of them is the failure.

Figures in the safety review are build tokens rather than literals, filled by
`tools/build_safety_review.py` from `ui/decisions.json`. A number that cannot
drift is a number nobody has to re-check.

The host-safety screen lives in `f2c/hostsafety.py` and is a gate in
`rank.py`: a refused candidate sorts below every unflagged one whatever it
scores, and nothing is dropped from the pool, so a refusal stays auditable.
The same screen covers reagents the warehouse has never seen
(`PROPOSED_REAGENTS`), which is how the carrier document's Stage 0 collagenase
is refused by the same mechanism rather than by a separate argument.


## Designing a variant, end to end

Two tools answer the chief biologist's two questions, and both write their
numbers into the protocol page rather than being quoted by hand.

    python -m tools.design_construct --target TfH --mutate H208A \
        --remove-signal-peptide 40
    python -m tools.build_protocol

`tools/design_construct.py` verifies the wild-type residue at every mutated
position before touching it, trims the signal peptide, reverse-translates with
E. coli codon preferences, and backtracks one codon when methionine or
tryptophan completes a restriction site — greedy selection alone produced an
ORF carrying internal NdeI and NcoI sites. The test suite translates the
result back through a standard codon table built independently of the tool's
own, so a round trip proves something.

`f2c/phsites.py` ranks titratable residues by how much a pH move changes their
ionisation, weighted by distance from the catalytic site measured at the atoms
that carry the charge. It is a shortlist to hand to PROPKA or constant-pH MD,
not a substitute for one, and it says so in its own output.


## Which arm is live

The project moved from polymer fragments to metals. `f2c/scope.py` holds that
as data: `ACTIVE_ARM`, a per-material `arm()`, and the banner text the
interface shows above anything from the earlier direction. The interface reads
it instead of deciding for itself.

This exists because a complete bench protocol was written around TfH, a PET
cutinase, weeks after the decision — correct work aimed at the arm the project
had left. A note in a page would not have prevented it; a default view and a
constant will.

Nothing polymer is deleted, and a test enforces that. The substrate
classifier, the catalytic-evidence signal and the host-safety screen were all
built in the polymer arm and all three now serve the metal one.

## The gap register

`f2c/gaps.py` records what the project does not know — eleven entries, graded
by consequence rather than by difficulty, each with what would close it and
who is placed to close it. Both protocol pages render it.

It is code rather than prose because a gap mentioned in a chat message is a
gap that disappears, and because neither of the team's two feasibility
documents raises a single item on the list. That is not a criticism of either:
a document answers the question it set out to answer, and these fall between
them.

Eight of the eleven have since closed, and they stay on the register with
`status`, `closed_on` and `closed_by`: the record of what was missing is worth
as much as the absence was. `residual` says where closing one left something
smaller behind, and an open entry carries `waiting_on` so it is not nobody's.

The entry to read first is `premise`, and it closed against the premise.
Rochkind 2014 (PMID 24898760) found that in shrapnel nerve injury the presence
of foreign particles predicts a *worse* outcome, 28% pain improvement against
67% without, and that nerve grafting beat neurolysis 100% to 47% — relieving
the compression is not what relieves the pain. Rochkind 2026 (PMID 42006932)
adds that about 55% of shrapnel nerve injuries carry the fragment inside the
nerve. The indication narrowed accordingly, in `pipeline.indication()` under
`what_the_evidence_does_not_support`, and on every current page.

## Building the protocol

    python -m tools.design_construct --target hFTH1 --uniprot P02794 \
        --mutate H65A --offset 1
    python -m tools.build_protocol

One builder emits both languages from one set of numbers, so the Hebrew and
English pages cannot disagree with each other or with the engine. The
ferroxidase site is verified against 1FHA on every build and the build fails
rather than publishing if any of the seven residues is wrong.


## Quantities the metal arm computes

| Function | Answers |
|---|---|
| `capacity` | ferritin mass the fragment demands |
| `chelator_demand` | deferoxamine mass, 1:1 with Fe(III) |
| `hydrogen_evolution` | H2 volume if the hydrogenase route runs |
| `timeline` / `carrier_placements` | how long, and how many injections |
| `released_elements` | every element dissolution frees, not only iron |
| `readout` | how anyone would know in a living subject |
| `enzyme_dose` | dose, given a rate — and a refusal without one |
| `aggregate` | all of the above across a patient's fragments |

Every one refuses a metal with no dissolution route and says why. That guard is
not decoration: giving stainless a composition silently made `capacity()` start
answering for it, and only the test caught it.

`COMPOSITION` replaced `METAL_FRACTION`, which carried the iron and discarded
the rest of the fragment. The rest is where the allergens are: nickel and
chromium are released by dissolution and deferoxamine does not bind either.
`METAL_FRACTION` survives as a derived view so existing callers keep working.
