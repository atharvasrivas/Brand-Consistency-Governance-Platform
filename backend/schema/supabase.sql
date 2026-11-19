-- Run once in the Supabase SQL editor. The API uses the service key, so Row Level Security is enabled with no
-- public policies: the table cannot be read or written with the anon key.
create table if not exists bg_docs (
  kind text not null,
  id text not null,
  data jsonb not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  primary key (kind, id)
);
create index if not exists bg_docs_kind on bg_docs(kind, created_at);
alter table bg_docs enable row level security;
-- Older tables from the first prototype (bg_profiles, bg_submissions) are no longer used and can be dropped.
