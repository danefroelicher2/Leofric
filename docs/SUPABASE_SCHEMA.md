# Supabase schema — recreate from scratch

Captured from the live project's OpenAPI spec on 2026-07-23, at shelving time.
Supabase's free tier pauses inactive projects and deletes them after extended
inactivity, so assume the original project is GONE by resurrection time. The
history it held is expendable — nothing in the system depends on old rows.

Run this in the SQL editor of a fresh Supabase project (or via the Supabase
MCP connector — the builder's preferred way to manage this DB):

```sql
-- Event log: one row per motion/person/identity event from any node.
-- metadata is jsonb so fields can be added without schema migrations
-- (e.g. snapshot_id was added in Phase 2B with zero DDL).
create table events (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  node_id     text not null,
  event_type  text not null,
  metadata    jsonb not null
);

-- Voice/app chat history: one row per utterance/reply.
-- session_id groups exchanges into threads (nullable: pre-2B rows had none).
create table conversations (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  node_id     text not null,
  session_id  text,
  role        text not null,          -- 'user' | 'assistant'
  content     text not null
);

-- RLS on, no policies: the anon key can touch nothing. The Pi node and the
-- Mac brain authenticate with the service_role key, which bypasses RLS —
-- they are trusted backends (see storage/events.py).
alter table events enable row level security;
alter table conversations enable row level security;
```

Then put the new project's URL + service_role key into the node's `.env` and
the brain's `.env` (templates: `.env.example`, `macmini/.env.example`).

Ordering queries in the code rely on `created_at`/`id` only; no indexes
beyond the primary keys were ever needed at single-home scale.
