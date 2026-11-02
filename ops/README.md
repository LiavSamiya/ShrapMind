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

Eight artifacts were published for this project. Four are current; the other
four are earlier work, kept rather than deleted. The directory that lists all
eight lives in the `#index` section of `ui/app.html`, so it ships with the
engine rather than existing only as a message in a chat.

| Page | Artifact | Source in this repo |
|---|---|---|
| ShrapMind (entry point) | `XQgkTkYvMmCjTXCqcXUr9H` | `ui/app.html` → `tools/build_app.py` → `ui/shrapmind.html` |
| Fragment-to-Catalyst Safety Review | `9NDiDW7T9dgooUJEGD9jYt` | `ui/safety-review.src.html` → `tools/build_safety_review.py` → `ui/safety-review.html` |
| ביקורת ארכיטקטורת ההידרוג'ל | `7vSe3aYcf4KM8KQKTzbfD5` | `ui/carrier-review.html` |
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
