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

Source code and SQL are implemented, but a hosted Supabase project, Google OAuth credentials and email delivery are not included. CI has applied the migrations to a disposable local Supabase stack and passed the synthetic multi-account RLS/messaging suite; this does not prove hosted authentication, OAuth, email delivery, or account deletion. See **Verification status** below before production use.

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

The GitHub Actions workflow runs this suite in a disposable local Supabase stack. The latest workflow run passed all 18 pgTAP assertions using three synthetic authenticated identities, covering public/private visibility, message-request authorization, accepted-message access, non-member denial, blocking and decline. This tests real PostgreSQL RLS locally, but is not a hosted-project or real-email-account smoke test. For that, create at least three dedicated test accounts and repeat the same scenarios in a configured Supabase project; do not use production personal accounts.

## Security boundaries and limitations

- Public/private enforcement and chat membership are enforced server-side by RLS. A private profile is hidden from discovery and feed content; an accepted chat partner may see the profile row, but private posts remain hidden.
- Messaging is private to accepted participants at the database/RLS layer and uses HTTPS in transit. It is **not end-to-end encrypted**; Supabase/database operators can access stored messages.
- Notifications are in-app and persisted in the database. Firebase/APNs push delivery is not implemented.
- Profile-photo upload/storage policies, moderation tooling for reviewing reports, and production release signing are not implemented.
- Account deletion requires the Edge Function to be deployed with the private server key. Without that deployment, deletion intentionally fails closed.

## Verification status

GitHub Actions run [39993488332](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/39993488332) passed the Android debug build, Kotlin unit tests, clean local Supabase migration/reset, and all 18 pgTAP assertions across three synthetic authenticated identities. The RLS/messaging suite covers private-profile/post visibility, request authorization, accepted-chat access, third-party denial, blocking, decline, and database notification rows. It is a local database integration test—not a hosted-project or real-email-account smoke test. Hosted email/password and Google OAuth, SMTP delivery, end-to-end Android messaging/notifications, deployed Edge Function account deletion, and production release signing remain unverified. Supply the Supabase URL/client key, Google OAuth Web client ID/secret, and SMTP configuration described above, then test those flows in a dedicated hosted test project before launch.

## Potential costs

A Supabase free project may be sufficient for development, but database/storage/egress limits, inactivity policies, and Edge Function quotas depend on the current plan. Production email delivery generally needs a custom SMTP provider (which may charge). Google OAuth is generally available without a per-sign-in fee, subject to Google's current terms. GitHub Actions usage is subject to the account's included minutes/storage. Publishing through Google Play requires a Play Console account and its current registration fee. Check each provider's current pricing before launch.
