## What's new in PlayReport 1.6 — new look: dark-first, cleaner, more readable
- A visual redesign only. The model, the probabilities, the selections, the data sources and every screen's content are exactly as before — nothing was added or removed; the app simply looks and reads better.
- Dark theme first (System / Light / Dark still under Settings → Appearance): a calm dark background, slightly lighter cards with thin borders instead of heavy shadows and gradients, one blue accent, and green / amber / red kept strictly for positive / caution / negative numbers.
- Clearer hierarchy: large key numbers with small labels, uppercase section captions, tighter and more consistent spacing, corner radius and iconography; tables and statistics laid out like an analytics terminal with subtle dividers.
- Home screen header is now a flat status strip — live status, update time and the day's key counts at a glance. The tennis section uses the same system with its green identity.
- Bottom navigation with a clear active indicator; pressed states and short, subtle screen transitions; nothing that slows the app down.
- New app icon: the roaring black panther bursting through a football / tennis ball, on the PlayReport blue. The splash screen matches the dark theme (no white flash on launch).

## What's new in PlayReport 1.6 — 🎾 Tennis on the home screen, selections of the day
- Sport switch at the top of every tab (⚽ Football 13 | 🎾 Tennis 34, with today's counts) — tennis is no longer hidden in the menu. Football screens are unchanged; the app remembers the sport you were on.
- A one-time card on the home screen points to the new placement after the update.
- Tennis is also on the football home screen itself: a "Tennis · selections of the day" strip right under the header numbers and the tennis card (grouped by market) right after Bets of the day — tap a row for the tennis match page, or "Open tennis" for the full section.
- Tennis Home: the day's selections grouped by market (Match winner / Total games / Player games / Game handicap) — one preferred market per match, ranked by model probability; strong markets; model-above-market flags; next matches; the tennis record.
- Selection rules (shown in the app): Sportybet price ≥ 1.30, model ≥ 60%, the bookmaker's margin-free probability ≥ 45% (it must not contradict the pick), data quality ≥ 60%, both players with 30+ rated matches, no low-confidence game data. STRONG = model ≥ 70% and market ≥ 50%. Not a "safe bet" list — a 70% selection loses three times in ten.
- Tennis Bets tab: selections, strong markets, model > market, all priced matches — with market filters. Live tab: ATP/WTA/Challenger scores from Livescore with set-by-set games. Matches tab with search. Days tab: every analysed day kept with results and how each selection settled.
- Match page rebuilt like the football one — Overview / Markets / Stats / Data: the selection with its reason and MODEL / FAIR / SPORTYBET / IMPLIED / EDGE; every market grouped with the preferred one flagged; side-by-side stats with sample labels (rating, last known ranking, form 5/10/20, surface form, serve & return, match profile); each player's last 10 matches with tournament, round, opponent, score and the model's pre-match expectation; head-to-head (context only); data-quality checks, player identity matching, model inputs and sources.
- Tennis tracker now grades four groups separately — selections of the day, strong markets, model-above-market flags and the rating favourite — with hit rate vs average model probability and flat-stake units. Reports and Telegram carry the same "Selections of the day" and "Strong markets" sections.

## What's new in PlayReport 1.6 — 🎾 Tennis (separate section, first release)
- New Tennis section in the menu (⋮ → 🎾 Tennis). It is completely separate from football: its own data, model, tracker and reports. Nothing in the football pages, selections or trackers has changed.
- Coverage: ATP, WTA and Challenger singles in the next 36 hours. Every match shows MODEL PROBABILITY for both players (they always add to 100%), the set-score probabilities (2-0 / 2-1, or 3-0 / 3-1 / 3-2 at Grand Slams), expected total games and a DATA QUALITY score with its 14 checks.
- Markets: match winner, total games, player games and game handicap — each with MODEL, FAIR ODDS, Sportybet ODDS, MARKET IMPLIED and EDGE. Bookmaker prices are a comparison only and never change a model probability. No tennis parlays.
- Highlights list model-above-market disagreements that pass the publication rules (price ≥ 1.30, model ≥ 55%, edge 5–20 pp, data quality ≥ 60, both players with 30+ rated matches). They are flags with evidence, not recommendations — the tennis tracker will show how they settle.
- Player evidence on every match: form (last 5 / 10 / 20 overall and on the surface), serve and return statistics with their sample size and date (marked stale when old), match profile (average games, straight-sets and deciding-set shares, tiebreaks). Missing statistics are shown as N/A, never as zero.
- Model validated on 288,000 matches (2005–2026) walk-forward with no look-ahead; details and calibration tables in tennis/BACKTEST_RESULTS.md.

## What's new in PlayReport 1.6 — results that stay, sounds you recognise
- Finished matches keep their final score, half-time score, match statistics (possession, shots, on target, corners, fouls, cards) and the goal timeline with scorers — also after they leave the live list. The Matches tab shows how many matches finished earlier today with a link to their results.
- Match statistics and goals are now collected for every competition Livescore publishes them for (before, only the big leagues playing that day were covered), so far more matches in the Days archive have full tables.
- Older matches (past 14 days) open an archive page from the day record: score, statistics, goals, the model's numbers at kick-off and how the bets settled. Nothing is lost when the detailed analysis is retired.
- Each notification type has its own short sound — goal, kick-off, half/full time, new selection, report published. Preview them under Settings → Notification sounds, or open the Android setting for any alert type from there.
- Editor card now shows Ndumiso Msani's photo.
- Small fixes: day-archive rows are always openable, "FT" shown consistently, fouls added to the statistics table.

## What's new in PlayReport 1.5 — data-first engine
- Every probability now comes from football data only. Bookmaker prices are shown next to the model as a separate comparison (implied %, difference in points, EV) and never change a model probability.
- Model xG and Market xG are shown separately on every match page — never blended.
- New Data tab on every match: data quality (High / Medium / Low with the reasons), the sample behind each team (matches, competitions, season, home/away, friendlies), home/away splits as plain historical frequencies, extreme results flagged, the raw matches used, head-to-head evidence strength, the model's own numbers ("why 1.35 goals?") and automatic checks and warnings.
- Every statistic carries its sample size: Very small (1–4), Small (5–9), Moderate (10–19), Strong (20–39), Very strong (40+). Historical frequency ("scored in 9 of 10") is always labelled apart from model probability and market implied.
- Markets tab: Model / Market / Diff / Price · EV columns; corners and cards show LOW DATA CONFIDENCE when the sample is thin.
- "Safest bets" are now called high-probability selections — a 75% probability still loses one time in four. Each one shows its data quality.
- Model update validated on 52,000 matches: team strength is shrunk less than goal tempo, which improves home/away win, Over 1.5 and Over 2.5 accuracy (details in backtest/RESULTS.md).
- CSV downloads include the data-quality assessment, the raw matches used and the model/market comparison.
