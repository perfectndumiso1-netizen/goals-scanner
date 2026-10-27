# Model review — why the winnings dropped (2026-10-27)

Scope: every settled selection in the three live ledgers published on the `data` branch.

| ledger | rows | date window | what it is |
|---|---|---|---|
| `shortlist.csv` | 5,696 (3,910 priced + settled) | 2026-10-09 → 2026-10-27 | every shortlist candidate, primary / watchlist / rejected |
| `safe_bets.csv` | 1,278 (977 graded) | 2026-09-26 → 2026-11-08 | the "strong markets" board (75 %+, odds ≥ 1.16) |
| `tracker.csv` | 550 (384 settled) | 2026-09-26 → 2026-12-19 | raw forward test of the model's own probabilities (no prices) |

Two housekeeping checks first, so the rest can be trusted:

* **Settlement is not the problem.** Every graded row in `shortlist.csv` (5,349) and `safe_bets.csv` (977) was
  re-graded from its stored scoreline with an independent implementation of `safe.settle`. **Zero mismatches.**
  The losing record is real.
* **Only priced rows are used for money maths.** 1,670 settled shortlist rows carry no odds; they are excluded
  everywhere below (`odds > 1`), otherwise the record looks ~2 pp worse than it is.

---

## 1. Bottom line

1. **The model is not beating the market it bets into — it is a little worse than it.** Over the 3,910 priced
   settled rows the de-vigged market price is a better forecast than our probability: Brier **0.1879 (market) vs
   0.1916 (model)**, log-loss **0.5608 vs 0.5705**. Mean `p_model − p_sb` = **+4.6 pp** — we are systematically
   overconfident, and the market knows better than we do.
2. **The loss is arithmetically unavoidable at the prices we take.** On primary picks we hold **+2.0 pp** of real
   edge over the de-vigged market, but the price we accept is **5.7 % of stake** worse than fair (implied 75.5 %
   vs fair 71.2 %). `0.020 / 0.712 − 0.057 ≈ −2.9 %` — exactly the −3.0 % observed. To break even we need ~4 pp of
   edge; we have 2.
3. **Two markets carry almost all the damage**, and they are the ones where our probability has no live price to
   check it against: **double chance −16.7 %** (n=300) and **team goals −6.4 %** (n=948, of which home-team-to-score
   **−10.1 %**, n=450). Cards −9.4 %. BTTS −7.0 %.
4. **Over 1.5 is not the broken lane.** `safe_bets` O1.5: **83.3 % hit vs 82.7 % predicted, −0.3 % ROI** (n=269).
   Shortlist O1.5: 78.6 % vs 77.9 %, −2.5 % (n=1,027). The two losing O1.5 weeks were 21 Sep → 4 Oct
   (−16.6 %, −7.6 %); the last three weeks are **+4.2 %, +2.3 %, +1.6 %**. What does lose on O1.5 is the
   *very short price*: the ≤ 1.14 band is **−4.0 %** (87 bets), and at 1.12–1.13 one bad weekend erases a good week.
5. **Nothing currently clears breakeven on its own.** Even the best lane (goals + corners, n=1,777) is **−0.8 %,
   90 % CI [−3.0 %, +1.3 %]**. The single largest realistic lever is **price**, not probability: a **+3 % better
   average price** (line-shopping two or three books instead of one) moves goals + corners to **+2.2 %** and the
   whole book to −1.3 %.

---

## 2. The record, as it stands

Priced + settled rows, `shortlist.csv`:

| segment | n | hit | model said | avg odds | ROI | 90 % bootstrap CI |
|---|---|---|---|---|---|---|
| all priced picks | 3,910 | 67.9 % | 70.5 % | 1.65 | **−4.2 %** | [−6.2, −2.0] |
| primary | 746 | 73.2 % | 73.6 % | 1.34 | **−3.0 %** | [−6.8, +0.5] |
| watchlist | 2,101 | 74.6 % | 76.6 % | 1.36 | **−3.4 %** | — |
| rejected | 1,063 | 51.0 % | 56.1 % | 2.4 | **−6.5 %** | — |
| goals + corners | 1,777 | 77.7 % | — | 1.30 | **−0.8 %** | [−3.0, +1.3] |
| `safe_bets` (safe) | 705 | — | — | — | −1.1 % | — |
| `safe_bets` (bet of the day) | 405 | — | — | — | −0.6 % | — |

The "rejected" bucket losing more than the accepted ones is the clearest sign that the ranking is not doing its
job: whatever we are rejecting, we are rejecting it for the wrong reason.

---

## 3. The arithmetic: edge bought vs margin paid

This is the heart of it. For each market: **gross edge** = actual hit rate − de-vigged market probability
(i.e. do we know something the market does not?); **margin** = implied probability of the price we took − de-vigged
probability (i.e. what we hand back to the bookmaker); **net** = hit − implied = the ROI driver.

| market | n | avg odds | model | de-vig market | implied | actual | **gross edge** | **margin** | net | **ROI** |
|---|---|---|---|---|---|---|---|---|---|---|
| `dc` (1X / X2 / 12) | 300 | 1.45 | 74.0 % | 66.7 % | 72.0 % | 62.0 % | **−4.7** | 5.3 | −10.0 | **−16.7 %** |
| `cards` | 37 | 1.36 | 71.2 % | 70.4 % | 75.3 % | 67.6 % | −2.9 | 4.8 | −7.7 | **−9.4 %** |
| `btts` | 183 | 1.67 | 58.8 % | 57.7 % | 62.4 % | 59.0 % | +1.3 | 4.7 | −3.4 | **−7.0 %** |
| `team` | 948 | 1.33 | 77.5 % | 70.7 % | 76.4 % | 71.6 % | +1.0 | 5.7 | −4.8 | **−6.4 %** |
| `result` (H/A) | 665 | 3.16 | 44.2 % | 39.8 % | 42.5 % | 41.7 % | +1.8 | 2.6 | −0.8 | **−3.3 %** |
| `goals` | 1,625 | 1.29 | 77.6 % | 74.1 % | 79.2 % | 78.2 % | **+4.1** | 5.1 | −1.0 | **−0.8 %** |
| `corners` | 152 | 1.40 | 71.9 % | 67.5 % | 72.4 % | 71.7 % | **+4.2** | 4.9 | −0.7 | **−0.5 %** |

Read it as a rule: **a market only survives if the gross edge is bigger than the margin.** Only goals (+4.1 vs
5.1) and corners (+4.2 vs 4.9) come close, and both are still a shade short. `dc` is not just short — it is
*negative* 4.7 pp against the market, so it loses twice: we are wrong **and** we pay the vig.

Within the families the damage is uneven and worth fixing line by line:

| selection | n | avg odds | model | actual | ROI |
|---|---|---|---|---|---|
| `HO05` home team to score | 450 | 1.28 | 79.4 % | 71.6 % | **−10.1 %** |
| `HU15` home under 1.5 | 57 | 1.43 | 72.7 % | 63.2 % | −13.7 % |
| `AO05` away team to score | 344 | 1.32 | 77.8 % | 72.7 % | −4.4 % |
| `AU15` away under 1.5 | 61 | 1.36 | 76.7 % | 78.7 % | +6.3 % |
| `O05` over 0.5 | 42 | 1.13 | 85.3 % | 83.3 % | −5.9 % |
| `O15` over 1.5 | 1,027 | 1.24 | 77.9 % | 78.6 % | −2.5 % |
| `O25` over 2.5 | 162 | 1.43 | 67.7 % | 71.0 % | +1.4 % |
| `U35` under 3.5 | 120 | 1.37 | 76.2 % | 73.3 % | +0.3 % |
| `U45` under 4.5 | 227 | 1.25 | 82.3 % | 81.5 % | +2.0 % |

Note the two lines that *do* pay are unders — which the product rule bans, so they are not a way out; they are
only evidence that the goals **model** is sounder than the goals **pricing**.

Double chance by selection, which shows the shape of the error:

| sel | n | model | de-vig market | actual | ROI |
|---|---|---|---|---|---|
| 1X | 173 | 77.1 % | 68.8 % | 62.4 % | **−18.1 %** |
| X2 | 83 | 65.5 % | 58.1 % | 57.8 % | −15.2 % |
| 12 | 44 | 77.9 % | 75.0 % | 68.2 % | −14.0 % |

The market was *right* on X2 (58.1 predicted, 57.8 actual) and we priced the same thing at 65.5 %. That is not a
run of bad luck, that is a broken probability for a market we should have had a price check on.

---

## 4. "Even over 1.5 totals" — the honest verdict

O1.5 is our best-understood lane and it is roughly at breakeven, not in collapse:

* `safe_bets` O1.5: **269 bets, 83.3 % hit against 82.7 % predicted, ROI −0.3 %.** Weekly: −16.6, −7.6, **+4.2,
  +2.3, +1.6**.
* `HO05` (the other lane the board leans on): 246 bets, 81.7 % vs 81.9 %, **−0.4 %**.
* The two bad weeks (21 Sep → 4 Oct) line up with **short prices**, not with the model: the O1.5 bets taken at
  **odds ≤ 1.14 returned −4.0 %** (87 bets, 86.2 % hit against a 89.7 % breakeven), while 1.14–1.20 returned
  **+2.6 %** and 1.20–1.28 **+15.5 %**.
* The raw unpriced forward test tells the same story with the volume turned up: `tracker.csv` O1.5 predicted
  **89.7 %**, happened **85.8 %** −3.9 pp. The *priced* version of the same market is accurate, because a price
  anchors it.

So: O1.5 feels like it broke because the price asked for it got shorter while the true rate stayed at ~83 %.
At 1.12 you need 89 %; you are going to lose even when you are right most of the time.

---

## 5. Is the model adding anything over the market?

No, at present. Blending our probability with the de-vigged market price, scored on all 3,910 priced settled rows:

| weight on our model | Brier | log-loss |
|---|---|---|
| 0.00 (market only) | 0.1879 | 0.5608 |
| **0.25** | **0.1879** | **0.5606** |
| 0.50 | 0.1885 | 0.5621 |
| 0.75 | 0.1898 | 0.5652 |
| 1.00 (today's `p_final`) | 0.1916 | 0.5705 |

The optimum is a **quarter weight on the model** — i.e. our probability carries a little information and a lot of
noise. Today `p_final` *is* `p_model` (`scanner.py:1236`, `:1282` — "nothing else is ever blended in"), so the app
and the videos publish the 1.00 column.

Reliability, all priced settled rows (where we say one thing and life says another):

| our p | n | we said | happened | error |
|---|---|---|---|---|
| ≤ 0.50 | 512 | 33.6 % | 28.5 % | −5.1 |
| 0.50–0.60 | 150 | 56.2 % | 57.3 % | +1.1 |
| 0.60–0.70 | 381 | 65.3 % | 68.8 % | +3.4 |
| 0.70–0.75 | 787 | 72.7 % | 69.4 % | −3.3 |
| 0.75–0.80 | 993 | 77.5 % | 75.9 % | −1.6 |
| 0.80–0.85 | 796 | 82.3 % | 78.0 % | **−4.3** |
| 0.85–0.90 | 272 | 86.5 % | 82.0 % | **−4.5** |
| > 0.90 | 19 | 91.1 % | 89.5 % | −1.6 |

Everything we are confident about is 1.5–4.5 pp too confident, exactly in the band the homepage advertises
(75 %+). And a price check confirms we are not even getting paid our own number: **65 % of picks were taken at a
price worse than our own fair price**, mean price / fair = **0.977**.

The unpriced forward test (`tracker.csv`) shows what happens without that anchor — and it is much worse:

| market | n | predicted | actual | error |
|---|---|---|---|---|
| **BTTS** | 135 | **69.5 %** | **54.1 %** | **−15.5** |
| O1.5 | 120 | 89.7 % | 85.8 % | −3.9 |
| O2.5 | 129 | 72.9 % | 73.6 % | +0.8 |

BTTS is **3.9 standard deviations** off (σ ≈ 4.0 pp at n=135) — not noise. It is also the market with **0 of 185
rows carrying a price**, i.e. precisely the market where nothing external can correct it. Among those 135 matches
the away side was blanked **30.4 %** of the time against 20 % in priced BTTS rows — the model is over-crediting the
weaker side's scoring. Meanwhile the *priced* BTTS rows in the shortlist are fine (58.8 predicted vs 59.0 actual),
which is the same lesson as the blend table: the price is doing the work, not the model.

---

## 6. League tier and ranking

Primary picks in England / Spain / Italy / Germany / France: **−7.7 %** (n=205) versus −1.3 % elsewhere (n=541) and
**+7.9 %** in UEFA competitions (n=56). But across the whole shortlist the top-5 leagues are fine (−0.7 %) and it is
the *rejected* bucket in those leagues that pays (+4.8 %, n=257). So the conclusion is **not** "avoid the big
leagues": it is that the *primary* flag mis-ranks them — in the leagues with the sharpest prices we are most likely
to mistake noise for edge, and we are promoting exactly those picks.

The composite score (`shortlist.py:196`: 40 % data quality + 40 % edge over the bar + 20 % confidence) does not
order picks monotonically by profit:

| score quartile | ROI |
|---|---|
| bottom | −2.8 % |
| 2nd | −5.9 % |
| 3rd | **−9.6 %** |
| top | +4.5 % |

Only the very top quartile earns; the 3rd quartile — the bulk of what gets promoted — is the worst. The score
rewards *distance above a probability bar*, which is the same quantity the model is overconfident about, so it
concentrates the error instead of filtering it.

---

## 7. Recommendations, in priority order

Each one is measured on the 3,910-row priced ledger, so the expected effect is not a guess. Changes are cumulative.

| # | change | n after | hit | ROI | CI |
|---|---|---|---|---|---|
| — | today | 3,910 | 67.9 % | −4.2 % | [−6.2, −2.0] |
| R1 | **drop double chance and cards** | 3,573 | 68.4 % | −3.1 % | [−5.2, −0.8] |
| R2 | **+ drop team goals (`HO05`, `HU15`, `AO05`)** | 2,722 | 67.5 % | −1.5 % | [−4.3, +1.3] |
| R3 | **+ drop `O05`** | 2,680 | 67.2 % | −1.5 % | [−4.2, +1.3] |
| R4 | **+ never take a price below 1.16** | 2,576 | 66.3 % | −1.5 % | [−4.4, +1.4] |
| R5 | **+ shop the price (+3 % on the average taken price)** | 2,576 | — | **+1.4 %** | — |

**R1 — stop publishing and stop betting double chance (`dc`) and cards.** −16.7 % and −9.4 % over 337 bets. The
model is *below* the market on double chance (−4.7 pp gross edge) and we pay 5.3 pp of margin on top. There is no
fix worth keeping here: remove `1X`/`X2`/`12` and the `K*` markets from the shortlist, the board, the videos and
the app. Expected gain: **+1.1 pp** of book ROI and ~9 % of the losing volume.

**R2 — stop home-team-goals; keep only away-team-goals if it must stay.** `HO05` alone is 450 bets at
**−10.1 %** and it is one of the two selections the board leans on most. `AO05` is −4.4 %, `AU15` +6.3 %. Cleanest
answer: **remove the team-goals family** and let O1.5 / O2.5 / corners carry the board. Expected gain: **+1.6 pp**.

**R3 / R4 — drop `O05` and never price below 1.16.** The 1.12–1.15 band is where a correct model still loses.

**R5 — shop the price, and this is the biggest lever.** **Never take the first price you see**: quote two or three
books and take the best, or skip the bet. A 3 % better average price is worth **+2.9 pp** on the book — more than
R1, R2 and R3 combined — and it is the only item on this list that improves every market at once, including goals and
corners (which go to **+2.2 %**). Implementation: record `best_price` alongside `p_sb`, publish the best price, and
add a hard gate "price ≥ 1.02 × the model's fair price" as a *sanity* check (today 65 % of picks fail it).

**R6 — anchor the published probability to the market.** Set `p_final = 0.25 · p_model + 0.75 · p_sb` wherever a
de-vigged price exists (best Brier and log-loss, see §5), fall back to `p_model` only when there is no price — and
when there is no price, **do not publish a number above 0.80** and mark it "unpriced". Also cap the displayed
probability at **0.84**, because the 0.80–0.90 band is where the overconfidence lives. This alone removes most of
the "75 %+ means safe" illusion on the home screen.

**R7 — raise the homepage floor from 75 % to 78 % and re-check it monthly against the ledger.** The 0.75–0.80
bucket is 993 bets at −2.8 %, so keeping 75 % as the promise is what makes the app *feel* wrong when it is merely
average.

**R8 — do not publish BTTS until it is recalibrated.** The forward test is 15.5 pp optimistic and has no price to
correct it; the priced BTTS rows are only fine because the market is doing the work. Either exclude BTTS from the
board/videos, or price it strictly off the de-vigged two-way BTTS market (which we already fetch: `safe.py:402`
`_two_way(yes, no)`) and treat the score-matrix BTTS as a tie-breaker only.

**R9 — replace the composite score with a market-anchored one.** Drop the "distance above the bar" term (it
amplifies the overconfidence). Rank by `p_sb`-anchored edge × price-vs-fair, and require, for primary status,
either **edge ≥ 4 pp with a live two-way quote** or a UEFA / non-top-5 fixture with edge ≥ 2 pp. The current middle
quartiles (−5.9 %, −9.6 %) are what a score like this looks like when it is sorting on the wrong thing.

**R10 — show the record honestly, per market, in the app and in the videos.** The app currently shows hit rates;
it should show ROI per market and per price band. The user's own experience ("winnings dropped") was visible in
this data weeks before it was visible in the bankroll.

---

## 8. What is *not* wrong (so it does not get "fixed")

* **Settlement.** 6,326 graded rows re-graded, zero disagreements. Corner and card regrading (`safe.regrade_settled`)
  is working.
* **The goals model in general.** O2.5 (+1.4 %), U3.5 (+0.3 %), U4.5 (+2.0 %) all pay; O1.5 is within 0.3 pp of
  breakeven on `safe_bets`. The goals engine is the part worth keeping.
* **Corners.** 152 bets, −0.5 %, gross edge +4.2 pp over the market — the second-best lane after goals.
* **Volume/selection breadth.** 63 % of the book is goals + corners and that is the right shape. The problem is the
  other 37 %.
* **The videos' market choice (O1.5 / corners / bookings).** O1.5 and corners are the defensible ones; bookings and
  team goals are the two that must go.

---

## 9. Caveats

* 3,910 priced settled rows is a small sample: a −3 % true ROI is only ~1.6 σ from zero for primary picks
  (CI [−6.8, +0.5]). What is *not* noise is the structural evidence: the market beats our probability on Brier and
  log-loss over the whole book, the gross-edge-vs-margin table, and the unpriced BTTS forward test at 3.9 σ.
* Corner and card rows settled before the 2026-10-21 regrade fix are corrected in the ledger by
  `regrade_settled`, but any *betting* decisions taken on them were made on wrong data.
* All prices are a single bookmaker's quotes (SportyBet, via `safe.py` `_two_way`). The line-shopping gain in R5 is
  an estimate (+3 % average), not measured — worth verifying against two books for a week before relying on it.
* `score_rank` in `shortlist.csv` is the composite `score` value, not a rank (see `shortlist.py:532`); the quartiles
  above are quartiles of that score.

---

## 10. What was implemented (2026-10-27, same day)

Every recommendation that does not depend on new market data is in code, in `policy.py` where a single gate reaches
every surface (shortlist, high-probability board, bets of the day, match pages, videos, in-app briefing, app home).

| # | rule | where |
|---|---|---|
| R1 | double chance (`1X`/`12`/`X2`) and cards (`K…`) dropped — not offered, shown, spoken or rendered | `policy.family_of` / `allowed` |
| R2 | team goals dropped (`HO05`, `AO05`, `HO15`, `AU15`) | same |
| R3 | `O05` dropped | same |
| R4 | nothing priced below **1.16** is offered, at any layer | `policy.PRICE_FLOOR`, `safe.selections`, `shortlist.MIN_ODDS`, app `worth()` |
| R5 | price check: under **95 % of the pick's own fair price** ⇒ watchlist, never a primary pick | `policy.price_check`, `shortlist.evaluate` |
| R6 | published probability = **0.25 × model + 0.75 × de-vigged market**, capped at market + 3 pp and 90 % (80 % unpriced); raw model kept as `p_model` in every ledger | `policy.publish_p`, `safe.Sel.p`, `appdata._pp`, `shortlist` |
| R7 | home-page strong markets: **78 %** floor (was 75 %), Over 1.5 and corners only | `policy.STRONG_P_MIN` / `STRONG_RE`, `appdata.STRONG_CAPS` |
| R8 | BTTS off every board (still priced and shown as information on the match page) | `policy.allowed` |
| R9 | shortlist score = market-anchored edge + price quality, not "distance above the bar" | `shortlist.evaluate` |
| R10 | videos and the in-app briefing carry Over 1.5 + corners only | `shortlist_reel.REEL_MARKET_RE`, `pages.js reelMarket` |

Not implemented, and deliberately: **R5's line shopping** needs a second bookmaker feed before it can be measured, and
the +3 % assumption above is still an estimate. It is the one change worth doing next.

Verification: the whole suite (`pytest tests/`, 413 tests including the new `tests/test_model_review_2026_10_27.py`)
passes. Every old family assertion was rewritten to the new rule rather than deleted, so a rollback via
`MODEL_MARKETS=all` is still covered by tests.
