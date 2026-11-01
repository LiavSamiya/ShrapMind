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
