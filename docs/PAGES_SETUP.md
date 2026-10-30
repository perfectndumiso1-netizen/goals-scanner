# Publish the Mr 2 Odds privacy-policy URL

The static public site is in `docs/`, with no JavaScript, external fonts, tracking pixels, sign-in gate or forms. `.nojekyll` serves the files directly rather than processing the other documentation as Jekyll templates.

After merging the site files, a repository owner must enable GitHub Pages:

1. Repository **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Choose **main** and **/docs**, then **Save**.
4. Wait for the Pages build/deployment to finish. Confirm these URLs load without a GitHub login:
   - `https://perfectndumiso1-netizen.github.io/goals-scanner/`
   - `https://perfectndumiso1-netizen.github.io/goals-scanner/privacy-policy.html`

The initial Pages API check reported `has_pages:false`. The connected GitHub integration rejected Pages creation with HTTP 403; adding site files does **not** itself enable hosting. Do not claim the URL is live until the site is enabled and deployment verified. No new video/app release or publishing workflow is needed.

## Review and Google configuration

The policy covers the current Android implementation, local storage, Android backup preferences, provider request metadata, voluntary support, and optional operator-only Drive (`drive.file`) / YouTube (`youtube`, broad management access) integrations. The developer contact matches the existing app contact. The owner should review the commitments and keep them consistent with actual operations, including any separate Zapier publishing setup.

Use **Mr 2 Odds** consistently in Google's application branding and the policy URL above; the homepage URL is the first URL listed. If Google requests domain ownership verification or additional OAuth/YouTube review, those are separate requirements. A hosted privacy policy alone does not establish Google approval or replace accurate Play Data safety declarations. The existing APK has not been modified to add an in-app policy link by this site-only change.

Update the policy and effective date if data handling changes. Never publish OAuth secrets, access tokens or personal user records in this public site. Previous app identifiers are retained solely to describe compatibility accurately.
