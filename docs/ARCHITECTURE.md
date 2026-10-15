# Scanner architecture and operations

## Current stage boundaries

`scanner.main()` remains the run coordinator. Feed-specific parsing and matching live in source adapters (`worldfeed.py`, `sporty.py`, `livescore.py`, `news.py`), while model helpers, calibration, and shortlist logic remain independently testable modules. The first extracted transaction is app publication: `publication.publish()` owns the build → validate → promote boundary. The exporter writes only to staging; validation errors prevent promotion; promotion keeps a rollback copy for overwritten and pruned files; and staging is always removed. If rollback itself fails, the backup is retained and its path is logged for recovery.

The next low-risk refactor boundary is to extract ingestion and feature-building from `scanner.main()` without changing model inputs. Prediction and pick-selection behavior are intentionally unchanged in this upgrade.

## Run provenance

Each successful app-data publication includes `run_manifest.json` alongside `latest.json`. The manifest records the app schema version, model version, code revision when available, a SHA-256 fingerprint of the non-secret scanner configuration, run ID, generation time, feed counters, and key output counts. `latest.json` keeps its existing version 3 contract; the manifest makes its version explicit without changing fields consumed by existing app builds.

Research records carry a per-record `schema_version`. Existing versionless records are migrated as version 1 on load; unsupported future versions are skipped with a warning rather than silently misread.

## Feed health and coverage alerts

The `feed_health` registry records aggregate request outcomes (`success`, `empty`, `error`) and cache outcomes (`cache`, `stale`). It never stores URLs, response bodies, tokens, or raw provider error messages. A failed/degraded provider or a greater-than-50% drop in key counts relative to the last successful publication is included in the run manifest and logged. Floors suppress noise when normal counts are small.

## Evaluation gates

`backtest/backtest.py` reports post-training season holdouts, calibration, log-loss, Brier score, ROI at opening and closing market prices, and a no-vig opening-to-closing probability shift for O2.5 picks. The line-shift metric is a historical market proxy, not a claim about an individual bet's executed price. New scoring or selection rules should keep the test-season results separate from parameter selection and be compared against the current production baseline.

## Reproducibility

Runtime and test dependencies are hash-locked in `requirements.txt` and `requirements-test.txt`, generated from the human-maintained `requirements.in` and `requirements-test.in` inputs. Regenerate with `pip-compile --generate-hashes --output-file requirements.txt requirements.in` and `pip-compile --generate-hashes --output-file requirements-test.txt requirements-test.in`. CI installs with `--require-hashes`. GitHub Actions dependencies are recorded in the generated `.github/workflows/actions.lock`; use the GitHub CLI `gh actions-lock` to regenerate it after workflow/action-reference changes. Dependabot is configured for both Actions and pip updates so lock changes arrive as reviewable pull requests. GitHub documents workflow lockfiles as a public-preview feature; the repository lockfile is generated and verified, but activating an organization-wide **Require lockfile** policy is a separate administrative decision. See [GitHub's lockfile overview](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles) and [enforcement guidance](https://docs.github.com/en/actions/how-tos/administer/enforce-workflow-lockfiles).
