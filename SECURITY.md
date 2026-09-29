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
