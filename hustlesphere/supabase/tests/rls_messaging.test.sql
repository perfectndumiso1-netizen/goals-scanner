-- Run with `supabase test db` after applying migrations 0001 and 0002.
-- Three synthetic identities exercise real authenticated-role RLS in one transaction.
create extension if not exists pgtap with schema extensions;
begin;
select extensions.plan(18);

insert into auth.users (
  id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
  ('11111111-1111-4111-8111-111111111111', 'authenticated', 'authenticated', 'hs-alice@example.test', '', now(),
   '{"provider":"email","providers":["email"]}'::jsonb, '{"name":"Alice Test"}'::jsonb, now(), now()),
  ('22222222-2222-4222-8222-222222222222', 'authenticated', 'authenticated', 'hs-bob@example.test', '', now(),
   '{"provider":"email","providers":["email"]}'::jsonb, '{"name":"Bob Test"}'::jsonb, now(), now()),
  ('33333333-3333-4333-8333-333333333333', 'authenticated', 'authenticated', 'hs-carol@example.test', '', now(),
   '{"provider":"email","providers":["email"]}'::jsonb, '{"name":"Carol Test"}'::jsonb, now(), now())
on conflict (id) do nothing;

-- Alice initially sees Bob's public profile.
select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select set_config('request.jwt.claims', '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select count(*) from public.profiles where id = '22222222-2222-4222-8222-222222222222'),
  1::bigint,
  'another member can read a public profile'
);
reset role;

-- Bob switches private and creates content while private.
select set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);
select set_config('request.jwt.claims', '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
set local role authenticated;
update public.profiles set visibility = 'private' where id = auth.uid();
with new_post as (
  insert into public.posts (author_id, category, body)
  values (auth.uid(), 'General', 'Private test post')
  returning id
)
select set_config('test.hustlesphere.private_post_id', id::text, true) from new_post;
select extensions.is(
  (select count(*) from public.profiles where id = auth.uid()),
  1::bigint,
  'a member can always read their own private profile'
);
reset role;

select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select set_config('request.jwt.claims', '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select count(*) from public.profiles where id = '22222222-2222-4222-8222-222222222222'),
  0::bigint,
  'a private profile is hidden from another member'
);
select extensions.is(
  (select count(*) from public.posts where id = current_setting('test.hustlesphere.private_post_id')::uuid),
  0::bigint,
  'posts from a private profile are hidden from another member'
);
reset role;

-- Bob makes his profile public, then Alice starts a request.
select set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);
select set_config('request.jwt.claims', '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
set local role authenticated;
update public.profiles set visibility = 'public' where id = auth.uid();
reset role;

select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select set_config('request.jwt.claims', '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);
set local role authenticated;
select set_config(
  'test.hustlesphere.request_ab',
  public.hustlesphere_send_message_request('22222222-2222-4222-8222-222222222222')::text,
  true
);
select extensions.is(
  (select status::text from public.message_requests where id = current_setting('test.hustlesphere.request_ab')::uuid),
  'pending'::text,
  'a message request begins pending'
);
select extensions.throws_ok(
  'select public.hustlesphere_accept_message_request(current_setting(''test.hustlesphere.request_ab'')::uuid)',
  '42501',
  'Only the recipient can accept this request.',
  'the sender cannot accept their own request'
);
reset role;

-- Bob accepts and creates the conversation through the atomic RPC.
select set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);
select set_config('request.jwt.claims', '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
set local role authenticated;
select set_config(
  'test.hustlesphere.conversation_ab',
  public.hustlesphere_accept_message_request(current_setting('test.hustlesphere.request_ab')::uuid)::text,
  true
);
select extensions.ok(current_setting('test.hustlesphere.conversation_ab') <> '', 'recipient acceptance creates a conversation');
select extensions.is(
  (select count(*) from public.notifications where recipient_id = auth.uid() and kind = 'message_request'),
  1::bigint,
  'message-request notification is created for the recipient'
);
insert into public.messages (conversation_id, sender_id, body)
values (current_setting('test.hustlesphere.conversation_ab')::uuid, auth.uid(), 'Private test message');
select extensions.is(
  (select count(*) from public.messages where conversation_id = current_setting('test.hustlesphere.conversation_ab')::uuid),
  1::bigint,
  'a conversation member can read a message'
);
reset role;

-- Alice is a participant and can see the accepted conversation message.
select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select set_config('request.jwt.claims', '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select count(*) from public.messages where conversation_id = current_setting('test.hustlesphere.conversation_ab')::uuid),
  1::bigint,
  'the other accepted participant can read the same message'
);
select extensions.is(
  (select count(*) from public.notifications where recipient_id = auth.uid() and kind = 'message_request_accepted'),
  1::bigint,
  'the requester is notified when the request is accepted'
);
reset role;

-- Carol is not a participant and must not see either the conversation or its messages.
select set_config('request.jwt.claim.sub', '33333333-3333-4333-8333-333333333333', true);
select set_config('request.jwt.claims', '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select count(*) from public.conversations where id = current_setting('test.hustlesphere.conversation_ab')::uuid),
  0::bigint,
  'a non-member cannot read a private conversation'
);
select extensions.is(
  (select count(*) from public.messages where conversation_id = current_setting('test.hustlesphere.conversation_ab')::uuid),
  0::bigint,
  'a non-member cannot read private messages'
);
reset role;

-- Blocking revokes the accepted request and makes the existing conversation unreadable.
select set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);
select set_config('request.jwt.claims', '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
set local role authenticated;
insert into public.blocks (blocker_id, blocked_id) values (auth.uid(), '11111111-1111-4111-8111-111111111111');
reset role;

select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select set_config('request.jwt.claims', '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select count(*) from public.messages where conversation_id = current_setting('test.hustlesphere.conversation_ab')::uuid),
  0::bigint,
  'blocking revokes access to the previous conversation'
);
reset role;

-- A different public pair can decline a request; this does not create a conversation.
select set_config('request.jwt.claim.sub', '33333333-3333-4333-8333-333333333333', true);
select set_config('request.jwt.claims', '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}', true);
set local role authenticated;
select set_config(
  'test.hustlesphere.request_cb',
  public.hustlesphere_send_message_request('22222222-2222-4222-8222-222222222222')::text,
  true
);
reset role;

select set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);
select set_config('request.jwt.claims', '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}', true);
set local role authenticated;
select public.hustlesphere_decline_message_request(current_setting('test.hustlesphere.request_cb')::uuid);
reset role;

select set_config('request.jwt.claim.sub', '33333333-3333-4333-8333-333333333333', true);
select set_config('request.jwt.claims', '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}', true);
set local role authenticated;
select extensions.is(
  (select status::text from public.message_requests where id = current_setting('test.hustlesphere.request_cb')::uuid),
  'declined'::text,
  'recipient can decline a request'
);
select extensions.is(
  (select count(*) from public.conversations where request_id = current_setting('test.hustlesphere.request_cb')::uuid),
  0::bigint,
  'declining does not create a conversation'
);
reset role;

select extensions.ok(
  not has_table_privilege('authenticated', 'public.conversations', 'INSERT'),
  'authenticated clients cannot insert conversations directly'
);
select extensions.ok(
  not has_table_privilege('authenticated', 'public.message_requests', 'UPDATE'),
  'authenticated clients cannot edit message-request status directly'
);

select * from extensions.finish();
rollback;
