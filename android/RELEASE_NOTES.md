## What's new — 🏠 New Home: every bet of the day, with Sportybet odds
- 🏠 **Home is now the day's betting board.** Every market (1X2, double chance, total goals, BTTS, team goals, corners, bookings) in one list — each bet clears its model bar (**1X2 ≥60%, corners & bookings ≥65%, every other market ≥70%**) **and** has a Sportybet price on it, shown next to the model probability.
- 📈 **High probability tab** — bets the model rates **≥70%** get their own tab.
- 🔎 Filter by market, sort by model probability, odds (high or low), kick-off or league, and tap any row for the full match page. Long days load 100 bets at a time.
- The top of Home keeps a short summary: today's numbers, live matches and the accas card. Signals, best of today and the explore links are still on the Scan tab.
- 🧊 Model untouched — prices are shown, never used to calculate a probability.

## Earlier — 🛡️ Play Protect clean · modern Android target · verified updates
- ✅ **The Play Protect warning is addressed at its source.** Two things caused it: the app was built for **Android 14 (API 34)** while the phone runs Android 17, which is exactly what triggers the "built for an older version of Android / unsafe app blocked" dialog — and it asked for the **install-other-apps permission**, which is what makes an app look like an installer. It now **targets Android 16 (API 36)** and no longer requests that permission at all.
- 🔐 **Updates are verified before Android sees them.** Every release publishes a SHA-256 digest; the app now checks the downloaded APK against it and **deletes anything that does not match**. The download also has to come from GitHub's own release hosts — the app will not download an update from anywhere else.
- 🧱 **The app can only talk to the services it actually uses** — the published analysis, live scores and crest images. Anything else is refused by the shell and by the page itself, so a corrupted data file cannot turn the app into a fetcher for whatever URL it contains.
- 🔒 **Installing is Android's job, not the app's.** The app never installs anything: it hands the verified file to the system installer with a read-only grant for that one file, and Android asks you. No install permission, no silent install.
- 🧊 **Everything else untouched** — the model, the accas, the boards, your tickets and favourites. This release is the app shell and its security only; the analysis behaves exactly as before.
- 📐 **The layout is right on modern Android** — targeting the current Android level means the system draws the app edge to edge and stops resizing the window for the keyboard, so the shell now reserves the status bar and navigation bar itself and lets the keyboard push the page up. On older phones nothing changes.
- 🛠️ Behind the scenes: the release build now fails on a security-relevant lint error instead of logging it, the host allowlist is unit-tested (lookalike hosts, credentials in a URL, scheme and port tricks), and cloud backup is explicitly limited to your own app preferences.

## What's new in PlayReport 1.6.39 — 🎯 Three accas a day at ~3.00, and no more fake value legs
- 🎯 **Today's accas** (More → Today's accas, or the card on Home): three builds at ~3.00, every day. Each one is built only from legs where the model beats the de-vigged market by a believable 2–12 points, uses the fewest legs that reach the price (2 legs cost about 15% in vig, 3 about 22%, six 1.20 legs about 40%), takes one market per match, and never shares a match with another build.
- 📊 **Your record, in units** — every build is written down with its model and market probability and settled against the final scores, so the page answers the only question that matters. Each card shows both honest numbers: what it returns if the model is right, and what it returns if the market is right.
- 🚫 **Fake value is quarantined** — a leg where the model towers 15+ points over the price (a friendly or a cup qualifier the model cannot rate: 0.6% priced against a 29% model) is labelled a data fault and hidden from the boards, instead of being sold as the day's best bet.
- 🔒 **Load to slip** puts a whole acca in the slip in one tap — and refuses a leg that has already kicked off.
- 🧊 **The model is untouched** — this adds a plan and a record; the probabilities and the boards behave exactly as before.

## What's new in PlayReport 1.6.38 — 🛠️ Storage error gone · notifications land on the event · real standings · Low odds tab
- 🗄️ **The "Could not reach the server (setItem … exceeded the quota)" error is fixed** — a full phone can no longer be mistaken for a broken connection. When the saved analysis no longer fits, the app trims it, frees the page cache, saves a lighter copy, and finally hands it to the app's own storage — and the analysis on screen is always the full one.
- 🔔 **Notifications open the exact event** — a goal, half-time, full-time, kick-off or new-selection notification takes you to that match, not to a tab: the alert now carries the fixture it belongs to, and tennis alerts open the tennis match. Works from a cold start too.
- 📊 **Standings are real standings** — competitions that are not a league (cups, qualifiers, play-offs, friendlies) no longer show an invented table with invented positions ("70th of 73" in the US Open Cup). League tables, group tables and group-stage tables are untouched; a cup now simply says there is no table.
- 🎯 **New tab: Low odds 1.19 – 1.45** — every market the bookmaker prices inside that window, for the day, in one list: tap a row for the match page, **+** to add it to the slip, and sort by **odds (low → high), odds (high → low), model probability, kick-off or league**. Today and tomorrow are one tap apart.
- 🎾 **Tennis no longer spins when the live feed is unreachable** — a failed refresh used to re-render, refresh and render again in a loop (battery and data drain). The rate limit now counts attempts, not successes.
- 🧊 **Model untouched** — probabilities, thresholds, selections, grading and the odds-never-filter rule are exactly as before; this release is storage, navigation and accuracy fixes plus one new list.

## What's new in PlayReport 1.6.37 — 🔎 No dead tap left behind
- 👆 **The tappability sweep is complete** — team names now open the team page in the last remaining spots: **Best of today** rows, **Bet advisor** lines, the Scan **top-priced & shortlist** tables, **live match cards**, the **head-to-head meetings table**, the **match-page standings table**, and the stats-tab record line (the one that says "Tap a team name for the full page" — now it really works).
- ✅ Everything from 1.6.36 stands: market rows open their fixture, signal notifications land on the signals, football first on Home, match alerts jump straight to the match.
- 🧊 **Model untouched** — navigation only.

## What's new in PlayReport 1.6.36 — 👆 Everything taps · signals land on signals · football first
- 👆 **Nothing is unclickable anymore** — every match and every team, wherever it appears, now opens:
  - **All-markets rows**: tap any selection (Over 1.5, corners, bookings, BTTS…) → that fixture's Match Center, exactly like AiScore.
  - **Team names everywhere** → the club's stats page: match lists, Today's signals, High-probability boards, Bets of the day, ticket legs, league fixtures & results tables, head-to-head averages, form strips, line-ups and evidence cards. Tap the team name for the team page; tap anywhere else on the row for the match.
- 🔔 **Signal notifications land on the signals** — a "new high-probability selection" notification now opens the signals list itself (Scan → High probability) instead of a random tab. Kick-off, goal, half-time and full-time alerts still jump straight into that match.
- ⚽ **Football first on Home** — the Home page is football end to end (signals, best of today, your matches, next kick-offs); the tickets card, which can carry tennis legs, now sits below the football sections instead of above them.
- 🎨 **Feel** — tappable team names carry the pointer cursor; tap targets behave like the big score apps: row → match, name → team.
- 🧊 **Model untouched** — probabilities, thresholds, selections and grading exactly as before; navigation and presentation only.

## What's new in PlayReport 1.6.35 — 🗂️ All markets done right · 🔔 straight to the match
- 🗂️ **All six groups, always** — the All-markets page renders every group every time, in your order: **1X2 · Bookings · Corners · BTTS · Over 2.5 · Over 1.5**. A group where nothing qualifies now shows as its own **empty group card** ("…the group stays in place") instead of disappearing, so the page never reshuffles around gaps. Each header carries a live count ("12 picks · high to low" / "52 matches · strongest first"), and a summary line up top states how many matches were analysed today and how many selections made the six groups.
- 🔄 **The page heals stale data itself** — if the phone is holding an outdated analysis copy (exactly what left only the 1X2 block showing), opening the page fetches the latest analysis once and refills the groups automatically.
- 🔔 **Notifications open that match, straight** — tapping a **kick-off reminder, goal alert, half-time, full-time or new-selection notification now opens the exact match page** — no more landing on the Home or Live tab and hunting for the fixture. It works from a cold start too: the app finishes loading, then drops you on the match.
- 🎯 **Presentation pass** — model probability now uses the same colour-coded probability pill as every other board; kick-off, match, market-implied (±pp) and model columns line up across all groups.
- 🧊 **Model untouched** — probabilities, thresholds, the Safest O0.5/U5.5 drop and the both-under-1.15 exclusion are exactly as in 1.6.34.

## What's new in PlayReport 1.6.34 — 🗂️ All markets · sharper cuts · honest H2H averages
- 🗂️ **All-markets page** — one page for every market the model prices today, split into six groups in your order: **1X2 · Bookings · Corners · BTTS · Over 2.5 · Over 1.5**, each group sorted **strongest first (high → low)**. The 1X2 block leads with each match's strongest outcome and shows all three probabilities inline. Every other row shows kick-off, the match and selection, the market's implied % with the difference in points, the model % with its price and a one-tap add. Open it from the **All markets** chip on Home or from the More menu.
- 🧹 **Worthless prices cut everywhere** — a selection where **the model and the bookmaker both say under 1.15 odds** (model odds < 1.15 **and** price < 1.15) is dropped from every board — it can't carry value at either end. The match itself is never dropped: its other markets still show normally. This is the single exception to "odds never filter".
- 🎯 **Safest bets tighter** — **Over 0.5** and **Under 5.5** goals no longer take spots on the Safest board (they added no value there); everything else on the board is exactly as before.
- 📈 **Recent-goals averages on H2H** — the head-to-head tab now shows each club's **average goals scored and conceded over the last 5 and the last 10**, with the **home and away split** too — e.g. `last 10 1.40 / 1.20 · home · 5 1.60 / 0.80 · away · 5 1.20 / 1.60`. Straight from each club's matches on record (up to 10, newest first) — what happened, not a probability.
- 🧊 **Model untouched** — probabilities, calibration, the scanner and every existing board are unchanged; selection curation and display only.

## What's new in PlayReport 1.6.33 — 🎯 Smarter form window · scorelines · market truth
- 🧠 **A form window tuned on 52,000 matches** — the model now weighs the last **150 days** of form (was 120), blends home/away form more calmly, and reads up to **60 matches per team** (was 40). Every candidate had to beat the current settings on a held-out test season with **zero markets regressing** before it shipped — the calibration you rely on (home win ≥60% → 67% actual) is unchanged.
- ⚽ **Most likely scorelines** — every match's Overview shows the top three scorelines straight from the model's Dixon-Coles matrix (e.g. 1-1 13% · 1-0 11% · 2-1 9%) plus the probability they carry together.
- 📊 **Model vs the bookmaker** — the Performance page now publishes the honest head-to-head on held-out seasons: the market leads on 1X2 (it knows line-ups, injuries and where the money is), while the model sits within 0.007 of it on Over 2.5 **without ever seeing a price**.
- 💹 **Market bias, measured** — a 2023–26 study of 24,393 priced matches finds longshots priced 5–20% win *less* than the price implies (public money inflates them) and two Over-2.5 bands land *more* than implied. Shown as context on Performance — odds still never filter which matches you see.
- 🔬 **xG ratings tested — not adopted yet** — blending current-season xG into the ratings showed no proven gain on the available sample (the data only exists from 26/27); xG stays display-only and the test re-runs as the sample grows.
- 🧊 **Untouched:** selection thresholds, the odds-never-filter rule, shortlists, corners/cards models and every board definition — three proven parameters plus additive features only.

## What's new in PlayReport 1.6.32 — ✅ Team stats you can trust
- 📊 **"Averages per game" now really shows averages** — every team profile's box always carries **Goals for / game** and **Goals against / game** tiles next to the scoring counts, so the card says what the recent matches say instead of leaving you guessing.
- 🔢 **Real denominators, never a misleading "/10"** — "Scored in / Conceded in" now use the actual sample: **3/4 · last 4 matches** when a team has only played 4 this season (it used to claim 3/10). The same fix lands on the match Stats tab's scored row, where each side shows its own sample.
- 🚫 **No more fake zeros** — competitions that don't publish xG, shots on target, corners or cards now read **"not published for this competition"** instead of printing "xG in 0, shots on target in 0, corners in 0, cards in 0".
- 🏷️ **Honest labels** — xG and shots-on-target rows are marked "(last ≤10)" to match exactly how they're computed, and head-to-head form chips show the real window ("last 4: 7 pts" when only 4 matches exist).
- 🧊 **Model untouched** — scanner, probabilities, calibration and data pipeline exactly as before; display accuracy only.

## What's new in PlayReport 1.6.31 — 💪 Form-strip context · ⏪ H2H trend · 🔎 Teams fixed
- 💪 **Opponent-strength chips on the form strip** — every W/D/L badge in Recent form now carries a micro-marker: **▲ strong opponent · – average · ▼ weak** — the opponent's level relative to its own league (league-normalised attack/defence), so a run of wins against weak sides no longer looks like a run against strong ones. Tap a badge for the opponent and score.
- ⏪ **Head-to-head trend line** — the H2H card now opens with **"Last 5 meetings: Team A 3W · Draw 1 · Team B 1W · O2.5 4/5 · BTTS 3/5"** (up to the five most recent meetings) — the recent trend at a glance, on both live and archived matches.
- 🔎 **Teams page fixed** — tapping a club was opening an empty profile: the list passed a league name where the division id was required, so the data file never loaded. Rows now carry the correct division, missing files resolve through the global club index, and the page never sticks on the loading skeleton.
- 👤 **Founder profile** — the in-app profile now reads **Founder & Football Analyst** with a refreshed professional bio (age removed).
- 🧊 **Model untouched** — probabilities, calibration and grading exactly as before; presentation and context only.

## What's new in PlayReport 1.6.30 — ⚖️ Odds never filter
- 🚫 **No more "preferable odds"** — every minimum-price rule is gone: odds ≥1.30 / ≥1.25 / ≥1.15 floors removed from High-probability selections, ⭐ Bets of the day, Today's strong markets, Best of the day, the Bet advisor, the match page's top selections and Tennis selections of the day (tennis also drops its market-implied ≥45%/50% floors). A match is in or out on **model probability, data quality and form — never on its price**.
- 📉 **Market disagreements no longer hold a pick back** — a selection the bookmaker's price strongly disagrees with (model 72%, the price implies 45%) now appears on every board. The ⚠ marker and the Diff / EV columns still show the disagreement — they just don't hide the match anymore. Strong stats at high odds gets its place.
- 💬 **Honest copy everywhere** — the guide, card explanations, advisor, staking card, reports and tennis rules now say the price is shown for comparison but never used to filter; a new what's-new card explains the change.
- 🧊 **Model untouched** — probabilities, calibration, probability bars, form-backing rules and grading are exactly as before; this release only changes which priced selections are allowed onto the boards.

## What's new in PlayReport 1.6.29 — 🎯 Today's card, permanent archive, bet advisor
- 📅 **Selections are today's matches — never future fixtures**. Home's Today's signals, the high-probability board (Today by default, with a tap to see the next 60 days) and Today's strong markets now only ever list matches kicking off on this day.
- 🧭 **Bet advisor of the day** — new page (☰ menu and More): the day's card section by section, the biggest model-vs-market edges, the strongest signals and the high-confidence list, plus a staking-discipline card. Everything is model output — nothing is chosen by hand.
- ⭐ **1X2 is back on the card — five picks a day** — 1X2 now claims its matches first (up to five a day) and **Over 2.5 gets its guaranteed place next**, so the Goals block can no longer crowd them out. Same bars as before: ≥70% on both model and market view with form backing.
- 🗂️ **Nothing is ever deleted** — every analysed fixture, detail file, day archive, statistic and report is now kept permanently (it was 14/60 days). Once the model captures a match, it stays on record forever.
- 🗞️ **News you can trust, read inside the app** — headlines come from reputable outlets only (BBC, Sky Sports, The Guardian, ESPN, Goal, official competition sites, national papers and major local sources). Tap a headline and the article is **downloaded and saved on your phone** for reading inside PlayReport — no browser redirect; "Open original" is one tap away.
- 📝 **Match report tab** — finished matches grow a **Report** tab: the scoreline, half-time, shots, possession, corners and cards, the goal timeline, and how every model market fared against the real outcome (✓ landed / ✗ missed). The same report card appears at the top of every archived match.
- 🔗 **Previous matches are clickable everywhere** — head-to-head meetings, recent-form lists and the team page's "Last N matches" all open the full match page with the captured statistics; days are sortable (newest/oldest) under the Analysed fixtures list.
- 🧊 **Model untouched** — same probabilities, same calibration; selection policy and presentation only.

## What's new in PlayReport 1.6.28 — 🎨 The redesign, screen by screen
- 🏠 **Home rebuilt like the reference design** — date headline, the **TODAY** tile row (matches · analysed · high confidence · live), a **Today's signals** hero card showing the strongest signal with both crests, the full home/draw/away model view and the model/market/price strip (**View all** opens the whole list), and a **Best of today** card straight into the graded shortlist.
- 🔭 **Scan screen** — three summary cards with coloured icon tiles: **High model probability**, **Model > Market** and **Strong data**, each with its live count and one tap to the matching list, plus the date pill and today's boards below.
- ⚽ **Live screen, reference layout** — every followed match is now its own card: minute badge (LIVE xx' / FT / kick-off), both clubs with crests and score, the Over 2.5 model view, a plain-language verdict, and the selection chips + goal scorers underneath.
- 🧭 **More screen as a list** — Days, Leagues, Teams, Performance, Tickets, Best of the day, Guide, Analysis, Tennis, Settings, CSV and WhatsApp as icon rows with subtitles (and a pending-tickets badge), under the version card.
- 📊 **Performance upgraded** — All-time card (selections · hit rate · average model), a **Calibration** card comparing predicted vs actual with a verdict, and **Market types** icons that jump to the right Scan board. The detailed tables stay underneath.
- 🎯 **Match Center** — the Model card now leads with **1X2 rings** (home win · draw · away win) exactly like the reference, above the expected-goals comparison.
- 🧊 **Model untouched** — probabilities, calibration, data pipeline and every feature exactly where they were; presentation only.

## What's new in PlayReport 1.6.27 — 🎨 New look, same engine
- 🌙 **A fresh visual design** — deeper dark theme, cleaner cards and pill-shaped filters everywhere. High-probability selections now arrive as proper signal cards: both clubs with crests, the model's home / draw / away view, and the pick's model probability, market view and Sportybet price side by side.
- 📱 **New bottom navigation** — **Home · Scan · Live · Matches · More**. Scan opens today's board in one tap, with summary cards for high model probability, model-vs-market, strong data and today's top signals.
- 🧭 **More hub** — Days, Leagues, **Teams**, Performance, My tickets, Best of the day, the market guide, full analysis, Tennis, Settings, CSV and WhatsApp all live in one place, plus a live snapshot (matches analysed, high confidence, today's signals, live now).
- 🔎 **Team search** — find any club in the fixture window by team, league or country and jump straight to its profile: form, venues, head-to-head and upcoming fixtures.
- 🧊 **Model untouched** — same probabilities, same calibration, same data pipeline and every feature exactly where it was; this release is presentation only.

## What's new in PlayReport 1.6.25 — 🔗 Everything tappable · 🏆 Best of the day · 📣 Instant updates
- 🔗 **Every fixture and team is tappable** — open any match from any league and any day: full analysis inside the 24-hour window, the head-to-head and goals kept for 14 days, and the day archive (scores, statistics, H2H) for 60 days. Fixtures beyond the analysis window open straight from Leagues into the archive — the old "outside the 24-hour window" dead end is gone.
- ⚔️ **Head-to-head, AiScore style** — the Match Center's head-to-head section now opens with both clubs' **recent form strips** (last five results, colour-coded) above the win/draw/win bar and the previous meetings. Archived matches keep their head-to-head too.
- 📊 **Two new groups on Today** — **Today's strong markets** (every market at 70%+ model probability whatever the odds, highest first) and **Value** (markets Sportybet misprices with the strongest model signals, biggest edge first, edge shown). Everything already on Today stays exactly where it was.
- 🏆 **Best of the day, backed by club form** — the ☰ menu's Best page now lists **the bets to enter today, section by market**: home wins, away wins, goals (O1.5 / O2.5 / BTTS / team goals), corners and bookings. Every pick clears its model bar first (results ≥60%, goals ≥70%, corners & bookings ≥65%, market not contradicting, price on) and each row shows the **club-performance evidence** behind it — one side's venue run against the other's road run ("unbeaten in 5 at home · 0 wins on the road"), scoring rates, expected corners/cards with the sample size and referee. Weekly league-style tables are gone; this page is about which coupons to fill in.
- 🕐 **Cleaner header** — the clock line is gone; kick-off times stay where they belong, on every match.
- 📣 **Instant update notifications, no pop-ups** — no banners and no modal dialogs. When a new version lands you get one Android notification like a goal alert — checked the moment you open the app, when it returns to the foreground, and every few minutes in the background (no 6-hour wait) — and **tapping it downloads and installs the update immediately**.
- 🧊 **Model untouched** — same input, same numbers; grouping and presentation only.

## What's new in PlayReport 1.6.2x — 📅 60-day fixture coverage + Sportybet deep links
- 📅 **Fixtures covered up to 60 days ahead, in every league** — the scanner now discovers and analyses matches across the next 60 days worldwide (not just today), so the model gathers form, statistics and context early and every match is analysed well before kick-off. The Leagues tab's fixture lists span the same window; the Matches tab still shows today's games as before.
- 🎫 **PlayReport tickets meet Sportybet** — every priced match, slip leg and ticket leg now has an **SB** link that opens the match directly in Sportybet (their live odds and slip), and tickets can be copied to the clipboard in one tap.
- 🧾 **Sportybet booking codes** — paste any Sportybet booking code (SportyBet's daily picks, Telegram groups, tipsters) on the slip screen and PlayReport loads it straight into Sportybet for you.
- 🎯 **Bets of the day = Sportybet markets** — the card only ever contains markets Sportybet actually prices (≥ 1.30), and each bet now labels its price as Sportybet's own.
- 🧊 **Model untouched** — same input, same numbers; this is coverage, navigation and presentation.

## What's new in PlayReport 1.6.2x — 📊 Full tables, team search, sort options, zero dead-ends
- 🔎 **Search now finds teams, not just leagues** — type any club in the Leagues search and it lists matching teams worldwide (with country and competition); the Matches search box finds teams, leagues and fixtures. Tap a team to open its profile.
- 📊 **Standings are now complete** — P · W-D-L · **GF** · **GA** · GD · Pts · Form, with **sort options** (points, goal difference, goals for, name) and dedicated **Home record** and **Away record** tables under the main table. Team pages show GF/GA in the league table too.
- 🗂️ **Sort options in the Leagues tab** — browse by Country (default), Name, Next fixture, Most played or Most teams.
- 🔗 **No more "Could not load this day"** — in the League Center, results older than the on-phone day archive (the last analysed days) simply show the final score instead of opening a missing page; recent results open the Match Center or the full day archive as before.
- ✨ **Cleaner, more readable tables everywhere** — aligned tabular numerals, wide tables scroll sideways on small screens, trend windows never clip.
- 🧊 **Model untouched** — presentation and data-navigation only; same input, same numbers.

## What's new in PlayReport 1.9 — 🌍 Worldwide coverage: 300+ competitions, match news, league trends
- 🌍 **Every competition on the public feed is now tracked and labelled** — 300+ competitions across 80 countries. Each league page shows its **data-quality status** from the scanner's coverage registry: active, model-eligible, insufficient history, provider publishes no stats, finished or data error. Accuracy first — thin leagues are labelled, never forced, and never filled with guesses.
- 📋 **Match Center grew**: every match now has **Form** (both clubs' last 10, all competitions, plus each club's recent home/away run), **Table** (full standings with both clubs highlighted, and their home/away records) and **News** — recent headlines about *this fixture* and each team (previews, line-ups, injury news), from Google News with source and publication date. Tap any headline to open the original article.
- 📈 **League Center grew**: every competition now has **Trends** (average goals, Over 0.5/1.5/2.5/3.5, BTTS, home/draw/away, home & away goals, clean sheets, failed to score, corners & cards — over Last 5/10/20, Season and Previous season, with a "last 10 vs season" change line), **Teams** (tap a club for its profile) and **News** about the competition and its leading teams.
- 🔎 **Global search**: the Matches search box now also finds **leagues and clubs**, not just today's fixtures.
- ⏱️ **Team pages** add a **Trends** tab: last 5/10/20, season and previous season — points per game, goals for/against, overs, BTTS, clean sheets, failed to score, scored/conceded in N.
- ✅ **Data quality everywhere**: every trend window needs a real minimum of matches — thinner windows show **N/A**, never 0. Corners/cards use only the matches whose statistics the provider publishes. Standings are the current season's table (backfilled earlier seasons live in Results and Trends, never mixed into the table).
- 🧊 **The prediction model is frozen**: same input, same numbers — verified by hash against the pre-upgrade baseline. News is **information only**: it is shown for your reference and is never read by the model, the market comparison or the selections. One bad league or one failed news query can no longer stop the worldwide scan; all data is cached on your phone with short refresh windows.

## What's new in PlayReport 1.8 — 🏆 Leagues: worldwide tables, results & fixtures
- New **Leagues** tab (bottom bar): every football competition on the public live feed, worldwide — 270+ leagues and cups, grouped by country, with a search box for league or country.
- Open any league for **Standings** (points, goal difference, last-five form), **Results** (the last 40 finished matches with half-time scores) and **Fixtures** (the next two days), grouped by day. Cup and knockout competitions show results and fixtures — no table, because a bracket is not a table.
- The archive now covers the big leagues continuously: the Premier League, LaLiga, Serie A, Bundesliga, Ligue 1, Championship, Primeira Liga, the Süper Lig, the Scottish Premiership and 40+ other top leagues are pre-loaded with the full current season plus two earlier seasons of results — and the South Africa Premiership (Premiership) is in there too, updated on every matchday.
- Everything updates automatically with the 30-minute scan; each page shows how fresh the data is. Knockout rounds and smaller leagues appear as they play, and stay in the archive afterwards.
- Data comes only from the public live-score feed's own archive — missing pieces stay blank (N/A), never filled with guesses. The betting model, its inputs and every published probability are untouched; this is a read-only browser on top of the world data the app already collects.

## What's new in PlayReport 1.7 — bet slip for both sports, favourites, new sounds
- 🎾 **Tennis bet slip**: tap **+** next to any priced tennis selection (Selections, Strong, Model > market, and every market on a match page) to add it to the same slip as football. One leg per tennis match (the newer pick replaces the earlier one); the slip shows a "🎾 tennis" tag on each leg. Tickets follow the matches and settle automatically: winner legs from the result, game markets from the final set scores — retirements void the game legs, exactly like the tennis tracker.
- ⭐ **Tennis favourites**: star any tennis match (match row or match page). Your matches appear on the tennis home screen, a Favourites filter lives on the Matches tab, and the app alerts you in the background when a favourite finishes (with the set score) plus kick-off reminders.
- ⭐ **Bets of the day, rebuilt as six blocks**: 1 · Goals (Over 1.5 & team goals) — 2 · Over 2.5 — 3 · BTTS — 4 · 1X2 — 5 · Corners — 6 · Bookings. Each block holds at most 7 of the strongest qualifying bets; if only one or two meet the bar, only those are listed, and an empty block disappears. No forced picks — the thresholds are unchanged.
- 🎾 **Tennis Selections of the day, the same idea**: three blocks in order — Winner, Player games, Total games — max 7 each, never padded.
- 🔊 **New notification sounds**: the goal alert is now a real crowd eruption with the stadium horn; tennis results get their own "serve & bounce" sound; locked tickets get a short fanfare when they settle (won or lost). Settings → Notification sounds previews every one, plus the referee whistle.
- ✨ **Polish pass**: cleaner layout on small screens (2×2 hero numbers, compact tables), stronger number hierarchy in the slip and day card, refined buttons and spacing. The model, probabilities, selections and data are untouched.

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
