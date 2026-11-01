-- ShrapMind knowledge base. Idempotent - safe to re-run via launch_db.sh.
-- Embedding dim is 384 (sentence-transformers/all-MiniLM-L6-v2).
-- Postgres 13+ provides gen_random_uuid() built-in (no pgcrypto needed).

create extension if not exists vector;

-- ---------------------------------------------------------------- knowledge

-- Enzyme families with measured kinetic records. This is the table the
-- BRENDA ingestion fills; the seed ships a small hand-checked subset so the
-- system is useful before any bulk import.
create table if not exists enzyme_families (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    ec_class text not null default '',
    reaction_class text not null default '',
    substrate_material text not null default '',
    -- k_cat, k_m_uM, t_opt_c, ph_opt, half_life_h, radius_nm, ...
    kinetics jsonb not null default '{}'::jsonb,
    -- assay conditions the kinetics were measured under. Carried because a
    -- k_cat measured at 70 degC on amorphous substrate says very little
    -- about 37 degC in serum, and the agent is required to say so.
    conditions jsonb not null default '{}'::jsonb,
    maturity text not null default 'research',
    source text not null default '',
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists enzyme_families_embedding_idx
    on enzyme_families using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists enzyme_families_material_idx
    on enzyme_families (substrate_material);

-- Literature precedents, with BOTH halves of each claim. The
-- what_it_does_not_prove column is the one that keeps the project honest,
-- and the agent is required to carry it into the final report.
create table if not exists precedents (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    claim text not null default '',
    what_it_proves text not null default '',
    what_it_does_not_prove text not null default '',
    citation text not null default '',
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists precedents_embedding_idx
    on precedents using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Per-material guidance, retrieved lazily by the get_material_notes tool so
-- the system prompt stays small.
create table if not exists material_notes (
    material text primary key,
    run_note text not null default '',
    explain_note text not null default ''
);

-- ---------------------------------------------------------------- runs

create table if not exists design_runs (
    id uuid primary key default gen_random_uuid(),
    case_summary text not null,
    passport jsonb not null default '{}'::jsonb,
    reaction_spec jsonb not null default '{}'::jsonb,
    steps jsonb not null default '[]'::jsonb,
    chosen_candidate jsonb,
    assay jsonb,
    success boolean not null default false,
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists design_runs_embedding_idx
    on design_runs using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists design_runs_created_at_idx on design_runs (created_at desc);

create table if not exists candidates (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references design_runs(id) on delete cascade,
    name text not null,
    parent_family text not null default '',
    edits jsonb not null default '[]'::jsonb,
    scores jsonb not null default '{}'::jsonb,
    provenance text not null default 'in-silico proposal',
    created_at timestamptz not null default now()
);

create index if not exists candidates_run_idx on candidates (run_id);

create table if not exists assay_results (
    id uuid primary key default gen_random_uuid(),
    candidate_id uuid references candidates(id) on delete cascade,
    conditions jsonb not null default '{}'::jsonb,
    timeseries jsonb not null default '[]'::jsonb,
    metrics jsonb not null default '{}'::jsonb,
    gates jsonb not null default '[]'::jsonb,
    gates_passed boolean not null default false,
    mass_balance_residual double precision,
    created_at timestamptz not null default now()
);

create index if not exists assay_results_candidate_idx on assay_results (candidate_id);

-- ---------------------------------------------------------------- approval

-- Nothing reaches validated_library on the hot path. The agent and the
-- reviewer dashboard both submit here; only an approval promotes a row.
-- Same chokepoint design as the system this is modelled on, for the same
-- reason: a simulation result is a hypothesis until a human with domain
-- knowledge says otherwise.
create table if not exists pending_candidates (
    id uuid primary key default gen_random_uuid(),
    type text not null check (type in ('add', 'delete')),
    library_id uuid,
    candidate_name text not null,
    material_family text not null default '',
    summary text not null,
    rationale text not null default '',
    candidate jsonb not null default '{}'::jsonb,
    assay jsonb not null default '{}'::jsonb,
    gates jsonb not null default '[]'::jsonb,
    run_id uuid references design_runs(id) on delete set null,
    submitted_by text not null default 'agent',
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected')),
    reviewer_note text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create index if not exists pending_candidates_status_idx on pending_candidates (status);
create index if not exists pending_candidates_created_at_idx
    on pending_candidates (created_at desc);

-- Candidates a reviewer has signed off as worth a wet-lab experiment.
-- Still not validated biology - validated *as a hypothesis worth testing*.
create table if not exists validated_library (
    id uuid primary key default gen_random_uuid(),
    candidate_name text not null,
    material_family text not null default '',
    summary text not null,
    candidate jsonb not null default '{}'::jsonb,
    assay jsonb not null default '{}'::jsonb,
    gates jsonb not null default '[]'::jsonb,
    approved_by text not null default 'reviewer',
    reviewer_note text,
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists validated_library_embedding_idx
    on validated_library using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists feedback (
    id uuid primary key default gen_random_uuid(),
    rating text not null check (rating in ('like', 'dislike')),
    success boolean,
    summary text,
    source text not null default 'browser',
    created_at timestamptz not null default now()
);
