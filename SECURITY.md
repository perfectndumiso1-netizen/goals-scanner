# Security policy — PlayReport (goals-scanner)

## How credentials are handled here

| Credential | Where it lives | Never in |
| --- | --- | --- |
| Telegram bot token + chat id | GitHub → Settings → Secrets and variables → Actions → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | code, workflows, reports, committed JSON |
| Android signing keystore | Offline store on the owner's side; in CI as `ANDROID_KEYSTORE_B64` plus `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | the repository (`.gitignore` blocks `*.p12`, `*.jks`, `*.keystore`, `passwords.txt`, `goals-scanner-keys/`) |
| Publishing to the data / tennis-data branches | the per-run `GITHUB_TOKEN` GitHub injects, used only inside the workflow | any file |
| Sportybet / Livescore / Sackmann data | public endpoints, no credentials | — |
| The app on your phone | no credentials: it only reads public JSON from this repo | — |

## Rules

1. **Never commit a credential** — this repo is public and history is permanent.
2. Use `secrets.*` in workflows, `os.environ` in Python, `System.getenv` in the Android build.
3. Guard before pushing (scans every git-tracked file, fast, no dependencies):
   ```bash
   python3 scripts/check_secrets.py
   ```
4. The same check runs on every push to `main` and every pull request: `.github/workflows/secret-scan.yml`. Red build = do not merge.

## If a secret is exposed (checklist)

1. **Rotate at the provider first** — assume any published value is already copied.
   - Telegram: BotFather → `/mybots` → your bot → *API Token* → Revoke, then update `TELEGRAM_BOT_TOKEN`.
   - Android keystore: if the keystore or its passwords leak, an attacker could sign updates. Generate a new keystore, bump the app version, and ship a fresh build (users re-install once).
   - GitHub token: Settings → Developer settings → revoke, then create a replacement with the narrowest scopes.
2. Update the Actions secret(s), and revoke any local copies.
3. Look for other copies: `grep -rIn "<the value>" --exclude-dir=.git .`
4. Remember a committed value stays in history; rotation is the real fix. A history rewrite is possible on request but never a substitute.

## What is scanned

Tokens and keys (GitHub, Telegram, AWS, Slack, Stripe, Google), private-key blocks, bearer headers, hard-coded key/password assignments and opaque 32-character secrets — while ignoring environment lookups, placeholders, and content hashes.

## The Android app: why Play Protect warns, and what this repo does about it

Play Protect judges an app on a few things it can see before it has ever run. Two of them are entirely in our
control, and both were wrong until v1.6.42:

| What Play Protect looks at | What it was | What it is now |
| --- | --- | --- |
| The API level the APK targets | `targetSdk 34` (Android 14) while phones run Android 17 — Google warns when an app is more than one SDK generation behind the device | `targetSdk 36` (Android 16), which is also the level Play has required since 31 August 2026 |
| Whether the app can install other apps | it declared `REQUEST_INSTALL_PACKAGES` | the permission is gone. It was never needed: an update is handed to the **system** installer with `ACTION_VIEW`, and Android asks the user |

The rest is what an app *does* once installed, and the shell is now as boring as it can be:

1. **It only talks to the services it needs.** `Security.kt` holds one allowlist (published analysis, live
   scores, crest images) and the page enforces the same list in `core.js`. Every request goes through it —
   including each redirect hop of a download — so the app cannot be used as a fetcher for an arbitrary URL.
2. **It never installs anything.** No `PackageInstaller`, no install permission: the downloaded APK is handed
   to the system installer with a read-only grant for that one file.
3. **Updates are verified before they are offered.** GitHub publishes a SHA-256 digest for every release
   asset; `Updater.download()` compares the bytes on disk with it and deletes anything that does not match.
4. **The page runs with no reachable origins.** No `file://` or `content://` access, no universal access from
   file URLs, no popups, no mixed content, no geolocation. External links are `https` only.
5. **Backups cover the user's own preferences and nothing else** (`res/xml/backup_rules.xml`,
   `data_extraction_rules.xml`).

### Verifying a release you downloaded

Every release lists a `sha256:` digest next to the APK. To check the file matches before installing:

```bash
# Android 12+:  sha256sum PlayReport.apk
# macOS:        shasum -a 256 PlayReport.apk
# Windows:      certutil -hashfile PlayReport.apk SHA256
```

The value must equal the digest shown on the release page. The app itself performs this check on every update
it downloads.

### What we cannot fix from inside the APK

An app installed from outside Google Play is, to Google, from an unknown developer — that is the residual
prompt on any sideloaded build, and no code change removes it. Publishing the app (even to a closed test
track) is what makes Play Protect trust it. If a device still blocks the install with a *specific* claim
rather than the generic "unknown developer" notice, the Play Protect appeal form takes the package name and
the signing certificate from a report in the Play Store app.

### Guards that keep this from coming back

- `tests/test_apk_security.py` — permissions, SDK levels, toolchain versions, the allowlists, the digest
  check and the WebView settings. Every one of them was verified by breaking it on purpose.
- `android/app/src/test/java/.../SecurityTest.kt` — the allowlist itself, probed with lookalike hosts,
  credentials in the URL, scheme downgrades and odd ports; runs before the APK is published.
