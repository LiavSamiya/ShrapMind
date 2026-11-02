-- ShrapMind proposals DB schema. Idempotent — safe to re-run via launch_db.sh.
-- Embedding dim is 384, matching the embedder in server/db/client.py.
-- Postgres 13+ provides gen_random_uuid() built-in (no pgcrypto needed).
--
-- Structure follows voodo's server/db/schema.sql: a vectorised store of what
-- the system has proposed before, plus a queue of changes a human reviewer
-- approves or rejects, plus lightweight end-of-run feedback.
--
-- What differs is who the reviewer is and what is at stake. In voodo an IT
-- admin approves a Windows fix. Here a biologist approves a claim about an
-- enzyme, and the cost of a wrong approval is a lab month. So two columns
-- exist that voodo has no need for:
--
--   evidence_level  — the engine already refuses to present a prediction as a
--                     measurement. A reviewer's agreement is a fifth level,
--                     `expert_review`, and it never promotes a row to
--                     `experimental`. Approving a proposal records that
--                     someone qualified believed it, not that anyone measured it.
--
--   verdict         — 'agree' and 'needs_experiment' are different answers and
--                     collapsing them into approve/reject would throw away the
--                     one the lab actually acts on.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- What the engine proposed: a catalyst for a material, with the reasoning and
-- the gaps it already knows about. The embedded text is the problem statement
-- ("PET fragment, 55% crystalline, deep muscle"), so a later identical case
-- finds this row before the engine spends anything re-deriving it.
-- ---------------------------------------------------------------------------
create table if not exists proposals (
    id uuid primary key default gen_random_uuid(),
    -- The case, in the words the engine was asked in.
    problem_summary text not null,
    material text not null,
    -- What it chose, and why. Mirrors f2c.schema.Decision.
    enzyme_name text,
    uniprot_accession text,
    score double precision,
    rationale text,
    gaps jsonb not null default '[]'::jsonb,
    -- 'experimental' | 'curated' | 'predicted' | 'assumed' | 'expert_review'.
    -- Never raised by review; see the note at the top of this file.
    evidence_level text not null default 'curated'
        check (evidence_level in
            ('experimental', 'curated', 'predicted', 'assumed', 'expert_review')),
    -- What the catalytic constants behind it were actually measured on.
    -- 'polymer' | 'oligomer' | 'model' | 'unknown'. Carried here because a
    -- proposal retrieved by similarity must arrive with this attached, or the
    -- retrieval quietly launders a chromogenic-ester kcat into a polymer claim.
    substrate_class text,
    embedding vector(384),
    created_at timestamptz not null default now()
);

-- Index choice, and a deliberate departure from voodo's schema.
--
-- voodo builds ivfflat indexes with lists = 100. ivfflat partitions the
-- vectors into that many lists and probes one of them per query by default,
-- so on a table holding fewer rows than lists almost every list is empty and
-- the query returns a fraction of the true nearest neighbours. Measured here
-- on three rows: ivfflat returned one, a sequential scan returned three.
--
-- It fails silently, which is what makes it worth avoiding. A reviewer asking
-- "has anyone already raised this objection?" gets an answer of "no" that
-- means "the index did not look there", and goes on to spend an hour
-- rediscovering a colleague's point.
--
-- hnsw has no list-count to get wrong and keeps its recall from the first row
-- to the millionth, at the cost of a slower build and more memory. For a
-- corpus in the hundreds that trade is free.
create index if not exists proposals_embedding_idx
    on proposals using hnsw (embedding vector_cosine_ops);

create index if not exists proposals_created_at_idx
    on proposals (created_at desc);

create index if not exists proposals_material_idx
    on proposals (material);

-- ---------------------------------------------------------------------------
-- The biologists' queue. Everything the AI wants to assert about biology lands
-- here first and waits for a human. Nothing writes to `proposals` except an
-- approval — that is the whole point of the table.
-- ---------------------------------------------------------------------------
create table if not exists pending_changes (
    id uuid primary key default gen_random_uuid(),
    type text not null check (type in ('add', 'delete', 'amend')),
    proposal_id uuid references proposals(id) on delete set null,
    problem_summary text not null,
    material text,
    enzyme_name text,
    -- The engine's reasoning, for the reviewer to argue with.
    rationale text,
    gaps jsonb default '[]'::jsonb,
    reason text not null,
    submitted_by text not null default 'engine',
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected')),
    -- The reviewer's answer. 'agree' and 'needs_experiment' both close the
    -- item, but only the second one puts work on a bench.
    verdict text check (verdict in
        ('agree', 'disagree', 'unconvinced', 'needs_experiment', 'out_of_scope')),
    -- 1 (guessing) to 5 (certain). Nullable: demanding a number from someone
    -- who has none manufactures data, which is the habit this project exists
    -- to break.
    confidence smallint check (confidence between 1 and 5),
    reviewer text,
    reviewer_note text,
    -- Anything the reviewer cites against the proposal. Checked, not trusted.
    cites_pmid text[],
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create index if not exists pending_changes_status_idx
    on pending_changes (status);

create index if not exists pending_changes_created_at_idx
    on pending_changes (created_at desc);

-- ---------------------------------------------------------------------------
-- Reviewer notes, embedded. "Has someone already raised this objection?" is
-- worth answering before a second biologist spends an hour reaching it alone.
-- ---------------------------------------------------------------------------
create table if not exists review_notes (
    id uuid primary key default gen_random_uuid(),
    change_id uuid references pending_changes(id) on delete cascade,
    reviewer text not null,
    note text not null,
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists review_notes_embedding_idx
    on review_notes using hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- End-of-run 👍/👎 on a proposal. Lightweight — keeps the engine honest about
-- whether the biologist found the answer useful, independent of the score the
-- engine gave itself.
-- ---------------------------------------------------------------------------
create table if not exists feedback (
    id uuid primary key default gen_random_uuid(),
    rating text not null check (rating in ('like', 'dislike')),
    proposal_id uuid references proposals(id) on delete set null,
    summary text,
    source text not null default 'browser',
    created_at timestamptz not null default now()
);

create index if not exists feedback_created_at_idx
    on feedback (created_at desc);

-- ---------------------------------------------------------------------------
-- Material name → canonical key. The engine knows 'PET'; a clinician writes
-- 'polyester fragment' or 'Dacron'. Same role as voodo's open_app_aliases.
-- ---------------------------------------------------------------------------
create table if not exists material_aliases (
    alias text primary key,
    canonical text not null
);

insert into material_aliases (alias, canonical) values
    ('polyester',              'PET'),
    ('dacron',                 'PET'),
    ('polyethylene terephthalate', 'PET'),
    ('nylon',                  'PA'),
    ('polyamide',              'PA'),
    ('polyurethane',           'PUR'),
    ('pla',                    'PLA'),
    ('polylactic acid',        'PLA'),
    ('rubber',                 'NR'),
    ('natural rubber',         'NR'),
    ('polycarbonate',          'PC')
on conflict (alias) do nothing;

-- ---------------------------------------------------------------------------
-- The queue the lab actually works from: what reviewers independently said
-- needs an experiment, most-corroborated first.
-- ---------------------------------------------------------------------------
create or replace view open_experiments as
select material,
       enzyme_name,
       count(*)                           as raised_by,
       round(avg(confidence)::numeric, 1) as mean_confidence,
       max(reviewed_at)                   as last_raised
from pending_changes
where verdict = 'needs_experiment'
group by material, enzyme_name
order by raised_by desc, last_raised desc;
