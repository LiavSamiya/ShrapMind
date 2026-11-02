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
| Fragment-to-Catalyst Safety Review | `9NDiDW7T9dgooUJEGD9jYt` | `ui/safety-review.html` |
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
