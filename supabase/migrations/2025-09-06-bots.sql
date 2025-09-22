-- Run this in Supabase Studio (SQL editor) with service role.
create table if not exists public.bots (
  id text primary key,
  name text not null,
  emoji text default '🤖',
  system_prompt text default 'You are a helpful assistant.',
  provider text default 'openai',
  model text default 'gpt-5',
  temperature double precision default 0.2,
  max_tokens integer default 800,
  tools_enabled boolean default false,
  created_at double precision default extract(epoch from now()),
  updated_at double precision default extract(epoch from now())
);

-- RLS
alter table public.bots enable row level security;
-- Simple permissive policy (tune later): allow authenticated to read; service role writes.
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='bots' and policyname='Allow read to authenticated') then
    create policy "Allow read to authenticated" on public.bots for select using (auth.role() = 'authenticated');
  end if;
end $$;

