-- Hardening migration for the original starter 0001 schema.
-- Keep 0001 immutable for projects that may already have recorded it as applied.
-- Apply all migrations before exposing the API; this migration replaces every
-- permissive starter policy and removes broad client-table grants.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to authenticated;

-- Add stricter checks for new/updated rows without failing an upgrade because of
-- legacy values already stored by an earlier starter build.
alter table public.profiles drop constraint if exists profiles_username_check;
alter table public.profiles add constraint profiles_username_format_check
  check (username ~ '^[a-z0-9_]{3,24}$') not valid;
alter table public.profiles add constraint profiles_display_name_length_check
  check (char_length(display_name) <= 80) not valid;
alter table public.posts add constraint posts_body_nonblank_check
  check (char_length(btrim(body)) between 1 and 5000) not valid;
alter table public.comments add constraint comments_body_nonblank_check
  check (char_length(btrim(body)) between 1 and 2000) not valid;
alter table public.messages add constraint messages_body_nonblank_check
  check (char_length(btrim(body)) between 1 and 5000) not valid;
alter table public.reports add constraint reports_reason_nonblank_check
  check (char_length(btrim(reason)) between 3 and 1000) not valid;

-- Resolve any legacy duplicate active pairs before adding the uniqueness guard.
with ranked as (
  select r.id,
         row_number() over (
           partition by least(r.sender_id, r.recipient_id), greatest(r.sender_id, r.recipient_id)
           order by case when r.status = 'accepted' then 0 else 1 end, r.created_at, r.id
         ) as pair_rank
  from public.message_requests r
  where r.status in ('pending', 'accepted')
)
update public.message_requests r
set status = 'declined'
from ranked d
where d.id = r.id and d.pair_rank > 1;

create unique index if not exists message_requests_one_active_pair_idx
  on public.message_requests (least(sender_id, recipient_id), greatest(sender_id, recipient_id))
  where status in ('pending', 'accepted');

create index if not exists posts_author_created_idx on public.posts(author_id, created_at desc);
create index if not exists post_likes_user_idx on public.post_likes(user_id, post_id);
create index if not exists message_requests_recipient_status_idx on public.message_requests(recipient_id, status, created_at desc);
create index if not exists message_requests_sender_status_idx on public.message_requests(sender_id, status, created_at desc);

-- Private, fixed-search-path SECURITY DEFINER helpers avoid policy recursion while
-- checking both directions of a block and accepted conversation membership.
create or replace function private.hustlesphere_is_blocked(p_user_a uuid, p_user_b uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select p_user_a is not null
     and p_user_b is not null
     and exists (
       select 1 from public.blocks b
       where (b.blocker_id = p_user_a and b.blocked_id = p_user_b)
          or (b.blocker_id = p_user_b and b.blocked_id = p_user_a)
     );
$$;

create or replace function private.hustlesphere_can_view_profile(p_viewer_id uuid, p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when p_viewer_id is null or p_profile_id is null then false
    when p_viewer_id = p_profile_id then true
    when private.hustlesphere_is_blocked(p_viewer_id, p_profile_id) then false
    else exists (
      select 1 from public.profiles p
      where p.id = p_profile_id
        and (
          p.visibility = 'public'
          or exists (
            select 1
            from public.conversations c
            join public.message_requests r on r.id = c.request_id
            where r.status = 'accepted'
              and ((c.user_a = p_viewer_id and c.user_b = p_profile_id)
                or (c.user_b = p_viewer_id and c.user_a = p_profile_id))
          )
        )
    )
  end;
$$;

-- Even an accepted chat partner cannot see posts/comments from a private profile.
create or replace function private.hustlesphere_can_view_content(p_viewer_id uuid, p_author_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when p_viewer_id is null or p_author_id is null then false
    when p_viewer_id = p_author_id then true
    when private.hustlesphere_is_blocked(p_viewer_id, p_author_id) then false
    else exists (
      select 1 from public.profiles p
      where p.id = p_author_id and p.visibility = 'public'
    )
  end;
$$;

create or replace function private.hustlesphere_can_access_conversation(p_viewer_id uuid, p_conversation_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select p_viewer_id is not null
     and exists (
       select 1
       from public.conversations c
       join public.message_requests r on r.id = c.request_id
       where c.id = p_conversation_id
         and p_viewer_id in (c.user_a, c.user_b)
         and r.status = 'accepted'
         and not private.hustlesphere_is_blocked(c.user_a, c.user_b)
     );
$$;

revoke all on function private.hustlesphere_is_blocked(uuid, uuid) from public, anon;
revoke all on function private.hustlesphere_can_view_profile(uuid, uuid) from public, anon;
revoke all on function private.hustlesphere_can_view_content(uuid, uuid) from public, anon;
revoke all on function private.hustlesphere_can_access_conversation(uuid, uuid) from public, anon;
grant execute on function private.hustlesphere_is_blocked(uuid, uuid) to authenticated;
grant execute on function private.hustlesphere_can_view_profile(uuid, uuid) to authenticated;
grant execute on function private.hustlesphere_can_view_content(uuid, uuid) to authenticated;
grant execute on function private.hustlesphere_can_access_conversation(uuid, uuid) to authenticated;

-- Remove the public-schema starter trigger function from client RPC execution,
-- then move profile creation into the non-API private schema.
drop trigger if exists on_auth_user_created on auth.users;
revoke all on function public.create_profile_for_new_user() from public, anon, authenticated;
create or replace function private.hustlesphere_create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, username, display_name)
  values (
    new.id,
    'member_' || substr(replace(new.id::text, '-', ''), 1, 12),
    left(btrim(coalesce(new.raw_user_meta_data ->> 'name', '')), 80)
  )
  on conflict (id) do nothing;
  return new;
end;
$$;
revoke all on function private.hustlesphere_create_profile_for_new_user() from public, anon, authenticated;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure private.hustlesphere_create_profile_for_new_user();

-- Drop every starter policy before replacing it. A permissive starter policy left
-- behind would OR with the new policy and undo the privacy guarantees.
drop policy if exists "read public profiles or own" on public.profiles;
drop policy if exists "insert own profile" on public.profiles;
drop policy if exists "update own profile" on public.profiles;
drop policy if exists "authenticated read posts" on public.posts;
drop policy if exists "create own posts" on public.posts;
drop policy if exists "edit own posts" on public.posts;
drop policy if exists "delete own posts" on public.posts;
drop policy if exists "authenticated read comments" on public.comments;
drop policy if exists "create own comments" on public.comments;
drop policy if exists "delete own comments" on public.comments;
drop policy if exists "read likes" on public.post_likes;
drop policy if exists "like as self" on public.post_likes;
drop policy if exists "unlike as self" on public.post_likes;
drop policy if exists "read own block rows" on public.blocks;
drop policy if exists "create own block" on public.blocks;
drop policy if exists "remove own block" on public.blocks;
drop policy if exists "read own message requests" on public.message_requests;
drop policy if exists "send request as self" on public.message_requests;
drop policy if exists "recipient updates request" on public.message_requests;
drop policy if exists "members read accepted conversations" on public.conversations;
drop policy if exists "members read messages in accepted conversations" on public.messages;
drop policy if exists "send messages in accepted conversations" on public.messages;
drop policy if exists "create own reports" on public.reports;
drop policy if exists "read own reports" on public.reports;
drop policy if exists "read own notifications" on public.notifications;
drop policy if exists "update own notifications" on public.notifications;

create policy profiles_read_visible on public.profiles
  for select to authenticated
  using (private.hustlesphere_can_view_profile(auth.uid(), id));
create policy profiles_update_self on public.profiles
  for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

create policy posts_read_visible on public.posts
  for select to authenticated
  using (private.hustlesphere_can_view_content(auth.uid(), author_id));
create policy posts_create_self on public.posts
  for insert to authenticated
  with check (author_id = auth.uid());
create policy posts_update_self on public.posts
  for update to authenticated
  using (author_id = auth.uid())
  with check (author_id = auth.uid());
create policy posts_delete_self on public.posts
  for delete to authenticated
  using (author_id = auth.uid());

create policy comments_read_visible on public.comments
  for select to authenticated
  using (
    private.hustlesphere_can_view_content(auth.uid(), author_id)
    and exists (select 1 from public.posts p where p.id = comments.post_id)
  );
create policy comments_create_visible_post on public.comments
  for insert to authenticated
  with check (
    author_id = auth.uid()
    and exists (select 1 from public.posts p where p.id = comments.post_id)
  );
create policy comments_delete_self on public.comments
  for delete to authenticated
  using (author_id = auth.uid());

create policy post_likes_read_visible on public.post_likes
  for select to authenticated
  using (
    private.hustlesphere_can_view_content(auth.uid(), user_id)
    and exists (select 1 from public.posts p where p.id = post_likes.post_id)
  );
create policy post_likes_create_visible_post on public.post_likes
  for insert to authenticated
  with check (
    user_id = auth.uid()
    and exists (select 1 from public.posts p where p.id = post_likes.post_id)
  );
create policy post_likes_delete_self on public.post_likes
  for delete to authenticated
  using (user_id = auth.uid());

create policy blocks_read_own on public.blocks
  for select to authenticated
  using (blocker_id = auth.uid());
create policy blocks_create_self on public.blocks
  for insert to authenticated
  with check (blocker_id = auth.uid() and blocked_id <> auth.uid());
create policy blocks_delete_self on public.blocks
  for delete to authenticated
  using (blocker_id = auth.uid());

create policy message_requests_read_participant on public.message_requests
  for select to authenticated
  using (
    (sender_id = auth.uid() or recipient_id = auth.uid())
    and not private.hustlesphere_is_blocked(sender_id, recipient_id)
  );

create policy conversations_read_members on public.conversations
  for select to authenticated
  using (private.hustlesphere_can_access_conversation(auth.uid(), id));
create policy messages_read_members on public.messages
  for select to authenticated
  using (private.hustlesphere_can_access_conversation(auth.uid(), conversation_id));
create policy messages_send_members on public.messages
  for insert to authenticated
  with check (
    sender_id = auth.uid()
    and private.hustlesphere_can_access_conversation(auth.uid(), conversation_id)
  );

create policy reports_create_valid_target on public.reports
  for insert to authenticated
  with check (
    reporter_id = auth.uid()
    and (
      (target_user_id is not null
        and target_user_id <> auth.uid()
        and private.hustlesphere_can_view_profile(auth.uid(), target_user_id))
      or (post_id is not null and exists (select 1 from public.posts p where p.id = reports.post_id))
      or (comment_id is not null and exists (select 1 from public.comments c where c.id = reports.comment_id))
    )
  );
create policy reports_read_own on public.reports
  for select to authenticated
  using (reporter_id = auth.uid());

create policy notifications_read_own on public.notifications
  for select to authenticated
  using (recipient_id = auth.uid());
create policy notifications_update_read_state on public.notifications
  for update to authenticated
  using (recipient_id = auth.uid())
  with check (recipient_id = auth.uid());

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

-- Only the app's required columns/actions are granted. RLS provides row filters;
-- column grants additionally prevent spoofing IDs, timestamps and moderation state.
revoke all on table public.profiles, public.posts, public.comments, public.post_likes,
  public.blocks, public.message_requests, public.conversations, public.messages,
  public.reports, public.notifications from anon, authenticated;
grant usage on schema public to authenticated;

grant select on public.profiles to authenticated;
grant update (username, display_name, bio, visibility) on public.profiles to authenticated;

grant select, delete on public.posts to authenticated;
grant insert (author_id, category, body) on public.posts to authenticated;
grant update (category, body) on public.posts to authenticated;

grant select, delete on public.comments to authenticated;
grant insert (post_id, author_id, body) on public.comments to authenticated;

grant select, delete on public.post_likes to authenticated;
grant insert (post_id, user_id) on public.post_likes to authenticated;

grant select, delete on public.blocks to authenticated;
grant insert (blocker_id, blocked_id) on public.blocks to authenticated;

grant select on public.message_requests, public.conversations to authenticated;
grant select on public.messages to authenticated;
grant insert (conversation_id, sender_id, body) on public.messages to authenticated;

grant select on public.reports to authenticated;
grant insert (reporter_id, target_user_id, post_id, comment_id, reason) on public.reports to authenticated;
grant select on public.notifications to authenticated;
grant update (read_at) on public.notifications to authenticated;
