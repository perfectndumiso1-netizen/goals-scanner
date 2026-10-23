-- HustleSphere initial schema.
-- Run in Supabase SQL Editor. Review policies before production use.

create extension if not exists pgcrypto;

create type public.profile_visibility as enum ('public', 'private');
create type public.request_status as enum ('pending', 'accepted', 'declined', 'cancelled');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text unique not null check (char_length(username) between 3 and 30),
  display_name text not null default '',
  bio text not null default '' check (char_length(bio) <= 500),
  avatar_url text,
  interests text[] not null default '{}',
  skills text[] not null default '{}',
  channel_links jsonb not null default '[]'::jsonb,
  visibility public.profile_visibility not null default 'public',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.posts (
  id uuid primary key default gen_random_uuid(),
  author_id uuid not null references public.profiles(id) on delete cascade,
  category text not null check (category in ('Sports','Betting','AI Tools','Technology','Online Income','General')),
  body text not null check (char_length(body) between 1 and 5000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.posts(id) on delete cascade,
  author_id uuid not null references public.profiles(id) on delete cascade,
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);

create table public.post_likes (
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

create table public.blocks (
  blocker_id uuid not null references public.profiles(id) on delete cascade,
  blocked_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id),
  check (blocker_id <> blocked_id)
);

create table public.message_requests (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null references public.profiles(id) on delete cascade,
  recipient_id uuid not null references public.profiles(id) on delete cascade,
  status public.request_status not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (sender_id <> recipient_id)
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_a uuid not null references public.profiles(id) on delete cascade,
  user_b uuid not null references public.profiles(id) on delete cascade,
  request_id uuid unique references public.message_requests(id) on delete set null,
  created_at timestamptz not null default now(),
  check (user_a <> user_b),
  check (user_a < user_b),
  unique (user_a, user_b)
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  sender_id uuid not null references public.profiles(id) on delete cascade,
  body text not null check (char_length(body) between 1 and 5000),
  created_at timestamptz not null default now()
);

create table public.reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references public.profiles(id) on delete cascade,
  target_user_id uuid references public.profiles(id) on delete set null,
  post_id uuid references public.posts(id) on delete set null,
  comment_id uuid references public.comments(id) on delete set null,
  reason text not null check (char_length(reason) between 3 and 1000),
  status text not null default 'open' check (status in ('open','reviewing','resolved','dismissed')),
  created_at timestamptz not null default now(),
  check (target_user_id is not null or post_id is not null or comment_id is not null)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_id uuid not null references public.profiles(id) on delete cascade,
  actor_id uuid references public.profiles(id) on delete set null,
  kind text not null,
  entity_id uuid,
  body text not null default '',
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create index posts_created_at_idx on public.posts(created_at desc);
create index posts_category_idx on public.posts(category, created_at desc);
create index comments_post_id_idx on public.comments(post_id, created_at);
create index messages_conversation_created_idx on public.messages(conversation_id, created_at);
create index notifications_recipient_created_idx on public.notifications(recipient_id, created_at desc);

alter table public.profiles enable row level security;
alter table public.posts enable row level security;
alter table public.comments enable row level security;
alter table public.post_likes enable row level security;
alter table public.blocks enable row level security;
alter table public.message_requests enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.reports enable row level security;
alter table public.notifications enable row level security;

-- Profile owner can manage their profile. Public profile visibility is enforced for reads.
create policy "read public profiles or own" on public.profiles
for select to authenticated
using (visibility = 'public' or id = auth.uid());

create policy "insert own profile" on public.profiles
for insert to authenticated with check (id = auth.uid());

create policy "update own profile" on public.profiles
for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- Feed posts are readable to signed-in members; authors manage their own posts.
create policy "authenticated read posts" on public.posts
for select to authenticated using (true);
create policy "create own posts" on public.posts
for insert to authenticated with check (author_id = auth.uid());
create policy "edit own posts" on public.posts
for update to authenticated using (author_id = auth.uid()) with check (author_id = auth.uid());
create policy "delete own posts" on public.posts
for delete to authenticated using (author_id = auth.uid());

create policy "authenticated read comments" on public.comments
for select to authenticated using (true);
create policy "create own comments" on public.comments
for insert to authenticated with check (author_id = auth.uid());
create policy "delete own comments" on public.comments
for delete to authenticated using (author_id = auth.uid());

create policy "read likes" on public.post_likes
for select to authenticated using (true);
create policy "like as self" on public.post_likes
for insert to authenticated with check (user_id = auth.uid());
create policy "unlike as self" on public.post_likes
for delete to authenticated using (user_id = auth.uid());

create policy "read own block rows" on public.blocks
for select to authenticated using (blocker_id = auth.uid() or blocked_id = auth.uid());
create policy "create own block" on public.blocks
for insert to authenticated with check (blocker_id = auth.uid());
create policy "remove own block" on public.blocks
for delete to authenticated using (blocker_id = auth.uid());

-- Users can see requests they sent or received. Recipients control accept/decline.
create policy "read own message requests" on public.message_requests
for select to authenticated using (sender_id = auth.uid() or recipient_id = auth.uid());
create policy "send request as self" on public.message_requests
for insert to authenticated with check (sender_id = auth.uid() and status = 'pending');
create policy "recipient updates request" on public.message_requests
for update to authenticated using (recipient_id = auth.uid()) with check (recipient_id = auth.uid());

-- Conversation reads require membership AND an accepted request.
create policy "members read accepted conversations" on public.conversations
for select to authenticated using (
  auth.uid() in (user_a, user_b)
  and exists (
    select 1 from public.message_requests r
    where r.id = request_id and r.status = 'accepted'
  )
);

-- Client-side inserts are intentionally not permitted for conversations.
-- Create conversations through a reviewed server-side RPC after acceptance.

create policy "members read messages in accepted conversations" on public.messages
for select to authenticated using (
  exists (
    select 1 from public.conversations c
    join public.message_requests r on r.id = c.request_id
    where c.id = conversation_id
      and auth.uid() in (c.user_a, c.user_b)
      and r.status = 'accepted'
  )
);
create policy "send messages in accepted conversations" on public.messages
for insert to authenticated with check (
  sender_id = auth.uid()
  and exists (
    select 1 from public.conversations c
    join public.message_requests r on r.id = c.request_id
    where c.id = conversation_id
      and auth.uid() in (c.user_a, c.user_b)
      and r.status = 'accepted'
  )
);

create policy "create own reports" on public.reports
for insert to authenticated with check (reporter_id = auth.uid());
create policy "read own reports" on public.reports
for select to authenticated using (reporter_id = auth.uid());

create policy "read own notifications" on public.notifications
for select to authenticated using (recipient_id = auth.uid());
create policy "update own notifications" on public.notifications
for update to authenticated using (recipient_id = auth.uid()) with check (recipient_id = auth.uid());

-- Profile creation trigger. Username is generated from the auth UUID; users can edit it later.
create or replace function public.create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, username, display_name)
  values (
    new.id,
    'member_' || replace(substr(new.id::text, 1, 8), '-', ''),
    coalesce(new.raw_user_meta_data ->> 'name', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.create_profile_for_new_user();

-- Production TODO: add a SECURITY DEFINER RPC that atomically accepts a request,
-- creates a conversation with ordered user IDs, rejects requests involving blocked users,
-- and validates that only the recipient can accept. Review all RLS policies before launch.
