# HustleSphere — native Android app

This is a separate Android application in `hustlesphere/`. It does not replace or modify the football scanner in the repository's root or `android/` directory. The client is Kotlin + Jetpack Compose; it is not a website or WebView wrapper.

## What is implemented in this source tree

- Email/password sign-up and sign-in.
- Google OAuth through the system browser using Supabase PKCE and the `hustlesphere://auth-callback` deep link.
- Editable username, display name, bio and public/private visibility.
- Supabase-backed feed and post creation, categories, likes, comments and reporting.
- Public-member discovery, message requests, recipient accept/decline, accepted conversations and persisted messages.
- Blocking, database-backed in-app notifications and account deletion through a caller-authenticated Edge Function.
- Row-level security, narrow table grants and database-side messaging/notification workflows.

Source code and SQL are implemented, but a hosted Supabase project, Google OAuth credentials and email delivery are not included. A successful APK compilation does not prove that live authentication, RLS, OAuth, messaging or deletion works. See **Verification status** below and run the database tests before production use.

## Build a debug APK

Requirements: JDK 17, Android SDK Platform 35 / Build Tools 35, and Gradle 8.11.1 (Android Gradle Plugin 8.9.2).

From this directory:

```sh
gradle --no-daemon assembleDebug
```

The APK is written to `app/build/outputs/apk/debug/app-debug.apk`. Supabase settings are optional at compile time; without them the app displays a configuration notice and does not make requests. To build a configured local APK, use the public client key only:

```sh
gradle --no-daemon \
  -PSUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co \
  -PSUPABASE_ANON_KEY=YOUR_ANON_OR_PUBLISHABLE_CLIENT_KEY \
  assembleDebug
```

The same values can be provided as `SUPABASE_URL` and `SUPABASE_ANON_KEY` environment variables. Do not commit credentials or put a Supabase `service_role` / secret key in Gradle properties, GitHub Actions build variables, or the mobile app. The debug APK is debug-signed and is not a Play Store release.

## Configure Supabase

1. Create a Supabase project and keep its service-role key private.
2. Apply `supabase/migrations/0001_initial_schema.sql`, `supabase/migrations/0002_security_hardening.sql` and `supabase/migrations/0003_social_workflows.sql`, in that order. With the Supabase CLI, from this directory use `supabase link --project-ref YOUR_PROJECT_REF` and `supabase db push`; alternatively run all three files in the SQL Editor. The `private` schema is intentionally not in the REST API exposed-schema list.
3. Copy the project URL and **anon/publishable client key** from Supabase API settings. Supply them at build time as described above. RLS, not secrecy of the client key, is the authorization boundary.
4. In **Authentication → Providers → Email**, enable email/password. Set the email-confirmation policy you want. Configure production SMTP and confirmation-email templates; the default shared email service is rate-limited.
5. In **Authentication → Providers → Google**, enter a Google OAuth **Web application** client ID and secret. In Google Cloud Console, allow the Supabase callback `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`. In Supabase **Authentication → URL Configuration → Redirect URLs**, allow the exact mobile URI `hustlesphere://auth-callback`. Google sign-in is browser-based PKCE; no Google client secret is placed in the APK. Test on the installed app after OAuth is configured.
6. Deploy the account-deletion function. Set its server-only key and deploy with the Supabase CLI:

   ```sh
   supabase secrets set SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
   supabase functions deploy delete-account
   ```

   The function validates the caller's access token and deletes only that caller. The service-role key exists only in Edge Function secrets. Never add it to the Android build.
7. Rebuild after changing the project URL/client key. The app's URI scheme is declared in `app/src/main/AndroidManifest.xml`.

## Database privacy and messaging test

A pgTAP integration test for three separate identities (public/private profile visibility, hidden private posts, request authorization, accepted-message visibility, non-member denial, blocking, and decline) is in `supabase/tests/rls_messaging.test.sql`.

Run it against a local Supabase stack after applying migrations:

```sh
supabase start
supabase db reset
supabase test db
```

For a hosted-project smoke test, create at least three test accounts. Make one profile private and verify it is absent from another account's Explore/feed results while its owner can still see it; create a public message request, accept it from the recipient account, verify both participants can read messages, and verify a third account cannot. Repeat with decline and then block; the blocked pair must lose conversation access. Do not use production personal accounts for this test. The SQL pgTAP test is authored but cannot be considered passed until it is run against a real Supabase database.

## Security boundaries and limitations

- Public/private enforcement and chat membership are enforced server-side by RLS. A private profile is hidden from discovery and feed content; an accepted chat partner may see the profile row, but private posts remain hidden.
- Messaging is private to accepted participants at the database/RLS layer and uses HTTPS in transit. It is **not end-to-end encrypted**; Supabase/database operators can access stored messages.
- Notifications are in-app and persisted in the database. Firebase/APNs push delivery is not implemented.
- Profile-photo upload/storage policies, moderation tooling for reviewing reports, and production release signing are not implemented.
- Account deletion requires the Edge Function to be deployed with the private server key. Without that deployment, deletion intentionally fails closed.

## Verification status

This checkout does not include Supabase project credentials, Google OAuth credentials, or email SMTP settings. Live account, OAuth, multi-account RLS/messaging, notification, and account-deletion tests therefore remain pending configuration. CI builds a debug APK and runs Kotlin unit tests; run the pgTAP suite against local/hosted Supabase to verify backend behavior before calling those features production-ready.

## Potential costs

A Supabase free project may be sufficient for development, but database/storage/egress limits, inactivity policies, and Edge Function quotas depend on the current plan. Production email delivery generally needs a custom SMTP provider (which may charge). Google OAuth is generally available without a per-sign-in fee, subject to Google's current terms. GitHub Actions usage is subject to the account's included minutes/storage. Publishing through Google Play requires a Play Console account and its current registration fee. Check each provider's current pricing before launch.
