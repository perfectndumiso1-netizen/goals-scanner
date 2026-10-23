-- Server-enforced social workflows, feed projection, and database-generated notifications.
-- Request transitions and conversation creation are atomic RPCs; clients cannot mutate
-- request status or insert conversations directly.

create or replace function private.hustlesphere_touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
revoke all on function private.hustlesphere_touch_updated_at() from public, anon, authenticated;

create trigger profiles_touch_updated_at
before update on public.profiles
for each row execute procedure private.hustlesphere_touch_updated_at();
create trigger posts_touch_updated_at
before update on public.posts
for each row execute procedure private.hustlesphere_touch_updated_at();
create trigger message_requests_touch_updated_at
before update on public.message_requests
for each row execute procedure private.hustlesphere_touch_updated_at();

create or replace function public.hustlesphere_send_message_request(p_recipient_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_sender_id uuid := auth.uid();
  v_visibility public.profile_visibility;
  v_request_id uuid;
begin
  if v_sender_id is null then
    raise exception using errcode = '42501', message = 'Authentication is required.';
  end if;
  if p_recipient_id is null or p_recipient_id = v_sender_id then
    raise exception using errcode = '22023', message = 'Choose another member to message.';
  end if;

  select p.visibility into v_visibility
  from public.profiles p
  where p.id = p_recipient_id;
  if not found or v_visibility <> 'public' then
    raise exception using errcode = '42501', message = 'Message requests can only be sent to public profiles.';
  end if;
  if private.hustlesphere_is_blocked(v_sender_id, p_recipient_id) then
    raise exception using errcode = '42501', message = 'Messaging is unavailable for this member.';
  end if;
  if exists (
    select 1 from public.conversations c
    join public.message_requests r on r.id = c.request_id
    where r.status = 'accepted'
      and ((c.user_a = v_sender_id and c.user_b = p_recipient_id)
        or (c.user_b = v_sender_id and c.user_a = p_recipient_id))
  ) then
    raise exception using errcode = '23505', message = 'A conversation with this member already exists.';
  end if;

  select r.id into v_request_id
  from public.message_requests r
  where r.status = 'pending'
    and r.sender_id = v_sender_id
    and r.recipient_id = p_recipient_id;
  if v_request_id is not null then
    return v_request_id;
  end if;

  insert into public.message_requests (sender_id, recipient_id, status)
  values (v_sender_id, p_recipient_id, 'pending')
  returning id into v_request_id;
  return v_request_id;
exception
  when unique_violation then
    raise exception using errcode = '23505', message = 'There is already an active request or conversation for this pair.';
end;
$$;

create or replace function public.hustlesphere_accept_message_request(p_request_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_request public.message_requests%rowtype;
  v_conversation_id uuid;
begin
  if v_user_id is null then
    raise exception using errcode = '42501', message = 'Authentication is required.';
  end if;
  select r.* into v_request
  from public.message_requests r
  where r.id = p_request_id
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'Message request not found.';
  end if;
  if v_request.recipient_id <> v_user_id then
    raise exception using errcode = '42501', message = 'Only the recipient can accept this request.';
  end if;
  if v_request.status <> 'pending' then
    raise exception using errcode = '23514', message = 'Only a pending request can be accepted.';
  end if;
  if private.hustlesphere_is_blocked(v_request.sender_id, v_request.recipient_id) then
    raise exception using errcode = '42501', message = 'Messaging is unavailable for this member.';
  end if;

  update public.message_requests
  set status = 'accepted'
  where id = v_request.id;

  insert into public.conversations (user_a, user_b, request_id)
  values (least(v_request.sender_id, v_request.recipient_id),
          greatest(v_request.sender_id, v_request.recipient_id),
          v_request.id)
  on conflict (user_a, user_b) do update
    set request_id = excluded.request_id
  returning id into v_conversation_id;

  return v_conversation_id;
end;
$$;

create or replace function public.hustlesphere_decline_message_request(p_request_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_request public.message_requests%rowtype;
begin
  if v_user_id is null then
    raise exception using errcode = '42501', message = 'Authentication is required.';
  end if;
  select r.* into v_request
  from public.message_requests r
  where r.id = p_request_id
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'Message request not found.';
  end if;
  if v_request.recipient_id <> v_user_id then
    raise exception using errcode = '42501', message = 'Only the recipient can decline this request.';
  end if;
  if v_request.status <> 'pending' then
    raise exception using errcode = '23514', message = 'Only a pending request can be declined.';
  end if;

  update public.message_requests
  set status = 'declined'
  where id = v_request.id;
  return true;
end;
$$;

revoke all on function public.hustlesphere_accept_message_request(uuid) from public, anon, authenticated;
revoke all on function public.hustlesphere_decline_message_request(uuid) from public, anon, authenticated;
revoke all on function public.hustlesphere_send_message_request(uuid) from public, anon, authenticated;
grant execute on function public.hustlesphere_accept_message_request(uuid) to authenticated;
grant execute on function public.hustlesphere_decline_message_request(uuid) to authenticated;
grant execute on function public.hustlesphere_send_message_request(uuid) to authenticated;

create or replace function private.hustlesphere_notify_comment()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_recipient_id uuid;
begin
  select p.author_id into v_recipient_id
  from public.posts p where p.id = new.post_id;
  if v_recipient_id is not null
     and v_recipient_id <> new.author_id
     and not private.hustlesphere_is_blocked(v_recipient_id, new.author_id) then
    insert into public.notifications (recipient_id, actor_id, kind, entity_id, body)
    values (v_recipient_id, new.author_id, 'comment', new.post_id, 'commented on your post');
  end if;
  return new;
end;
$$;

create or replace function private.hustlesphere_notify_like()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_recipient_id uuid;
begin
  select p.author_id into v_recipient_id
  from public.posts p where p.id = new.post_id;
  if v_recipient_id is not null
     and v_recipient_id <> new.user_id
     and not private.hustlesphere_is_blocked(v_recipient_id, new.user_id) then
    insert into public.notifications (recipient_id, actor_id, kind, entity_id, body)
    values (v_recipient_id, new.user_id, 'like', new.post_id, 'liked your post');
  end if;
  return new;
end;
$$;

create or replace function private.hustlesphere_notify_message_request()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if not private.hustlesphere_is_blocked(new.sender_id, new.recipient_id) then
      insert into public.notifications (recipient_id, actor_id, kind, entity_id, body)
      values (new.recipient_id, new.sender_id, 'message_request', new.id, 'sent you a message request');
    end if;
  elsif old.status = 'pending' and new.status = 'accepted' then
    if not private.hustlesphere_is_blocked(new.sender_id, new.recipient_id) then
      insert into public.notifications (recipient_id, actor_id, kind, entity_id, body)
      values (new.sender_id, new.recipient_id, 'message_request_accepted', new.id, 'accepted your message request');
    end if;
  end if;
  return new;
end;
$$;

create or replace function private.hustlesphere_notify_message()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_a uuid;
  v_user_b uuid;
  v_recipient_id uuid;
begin
  select c.user_a, c.user_b into v_user_a, v_user_b
  from public.conversations c where c.id = new.conversation_id;
  if v_user_a is null then
    return new;
  end if;
  v_recipient_id := case when new.sender_id = v_user_a then v_user_b else v_user_a end;
  if v_recipient_id <> new.sender_id
     and not private.hustlesphere_is_blocked(new.sender_id, v_recipient_id) then
    insert into public.notifications (recipient_id, actor_id, kind, entity_id, body)
    values (v_recipient_id, new.sender_id, 'message', new.conversation_id, 'sent you a message');
  end if;
  return new;
end;
$$;

create or replace function private.hustlesphere_decline_requests_on_block()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.message_requests r
  set status = 'declined'
  where r.status in ('pending', 'accepted')
    and ((r.sender_id = new.blocker_id and r.recipient_id = new.blocked_id)
      or (r.sender_id = new.blocked_id and r.recipient_id = new.blocker_id));
  return new;
end;
$$;

revoke all on function private.hustlesphere_notify_comment() from public, anon, authenticated;
revoke all on function private.hustlesphere_notify_like() from public, anon, authenticated;
revoke all on function private.hustlesphere_notify_message_request() from public, anon, authenticated;
revoke all on function private.hustlesphere_notify_message() from public, anon, authenticated;
revoke all on function private.hustlesphere_decline_requests_on_block() from public, anon, authenticated;

create trigger comments_create_notification
after insert on public.comments
for each row execute procedure private.hustlesphere_notify_comment();
create trigger likes_create_notification
after insert on public.post_likes
for each row execute procedure private.hustlesphere_notify_like();
create trigger message_requests_create_notification
after insert on public.message_requests
for each row execute procedure private.hustlesphere_notify_message_request();
create trigger message_requests_accept_notification
after update of status on public.message_requests
for each row execute procedure private.hustlesphere_notify_message_request();
create trigger messages_create_notification
after insert on public.messages
for each row execute procedure private.hustlesphere_notify_message();
create trigger blocks_decline_pending_requests
after insert on public.blocks
for each row execute procedure private.hustlesphere_decline_requests_on_block();

-- The view runs with the caller's table privileges and RLS policies (PostgreSQL 15).
-- Counts only include rows the current viewer is permitted to read.
create or replace view public.post_feed with (security_invoker = true) as
select
  p.id,
  p.author_id,
  p.category,
  p.body,
  p.created_at,
  p.updated_at,
  pr.username,
  pr.display_name,
  count(distinct l.user_id)::integer as like_count,
  count(distinct c.id)::integer as comment_count,
  coalesce(bool_or(l.user_id = auth.uid()), false) as liked_by_me
from public.posts p
join public.profiles pr on pr.id = p.author_id
left join public.post_likes l on l.post_id = p.id
left join public.comments c on c.post_id = p.id
group by p.id, p.author_id, p.category, p.body, p.created_at, p.updated_at,
         pr.username, pr.display_name;
revoke all on public.post_feed from anon, authenticated;
grant select on public.post_feed to authenticated;
