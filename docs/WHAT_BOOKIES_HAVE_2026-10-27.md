# What the bookmakers have that we don't

**Date:** 2026-10-27 · Follows `MODEL_REVIEW_2026-10-27.md` (the measured review) and the fixes in PRs #16–#20.

The question was: *"our model is missing something the bookies have."* Yes — but it is not a better goal model. Over
3,910 priced, settled selections the de-vigged market out-forecast us (Brier **0.1879 vs 0.1916**), and our measured
edge over those same fair prices was about **+2 points** while we paid about **5 points** of margin. A model that is
worse than the market and pays a margin cannot win on the same information. What they have that we do not is the
*inputs*, the *price discovery*, and the *volume*. Here is the honest list, with what is actually reachable from this
repo.

---

## 1. They price on underlying performance; we price on goals

| | bookmakers | this repo |
|---|---|---|
| attack / defence rating built from | shot volume, shots on target, xG where published, plus goals | **goals only** (`scanner.build_profile` → `att`/`dfc` from `gf`/`ga`) |
| shots on target (`hst`/`ast`), shots (`hs`/`as`), possession (`hposs`/`aposs`) | priced | **stored and shown, never used by the model** (`history.STAT_KEYS`, `quality.py`, `appdata` detail files) |
| xG | priced | stored where the source publishes it (`backtest` reads `HxG`/`AxG`), displayed, not modelled |

Goals are a **noisy realisation** of performance. A team that creates 2.0 xG a game and scores 1.0 is not getting
worse; it is unlucky, and the market prices the 2.0. We price the 1.0 and call it "form". This is the single biggest
gap and — importantly — **we already hold the data to close it**.

**Reachable:** yes, offline. Blend a shots-on-target-derived (or xG where available) attack/defence rating into
`att`/`dfc` with a weight, and measure Brier / log-loss / closing-line value on our own archive before shipping.
**Risk:** high if shipped unmeasured — that is exactly the overconfidence the review found. **Effort:** a backtest
study first (no production change), then one bounded model change.

## 2. They see the whole price board; we see one price at one moment

We take Sportybet's price when we first publish a pick (`odds_asof` even records when a price was carried forward).
Bookmakers see every book, the direction and speed of the moves, and the money behind them. They know the **closing
line**, which is the closest thing to a true probability that exists, and they shape the price to balance their book.

What this means practically: a pick that looks like value at 09:00 may be at fair (or worse) by kick-off, and we never
find out. **We are measuring outcomes (win/loss) when the cheaper, faster signal is the price.**

**Reachable:** the highest-value next build, and cheap. We publish every 30 minutes, so we can snapshot each pick's
price per run and compute **CLV** (closing price vs the price we took) the way `backtest/backtest.py` already does for
opening vs closing market averages. CLV becomes informative after **tens** of picks, not the thousands a win-rate
needs. It also gives the honest answer to "is our edge real?" without waiting a season.

**Effort:** small (append-only price history in `state/`, one report line). **Risk:** none to the model.

## 3. They price team news hours before it is public

Confirmed XIs, rotations, late fitness tests, cup-style rotation, manager changes. We have a lineups feed, a
projected-XI model (`lineup_proj`) and a bounded research layer (`docs/RESEARCH.md`), but all of it is **display or a
tightly capped adjustment**, never a pricing input — deliberately, because an unbounded news blend is how a model
starts believing its own stories. Bookmakers have reporters and traders on the team sheets; the XI moves a goals line
by several points.

**Reachable:** partly — we get confirmed XIs, but late and only for covered competitions. A measured, capped
"confirmed XI differs from projection" adjustment for goals and corners is feasible; injuries are not (no reliable
free feed).

## 4. They have volume, we have 152 corner picks

A bookmaker's corner market is priced off millions of comparable matches, with traders who can cross-check a line
against related markets (Asian totals, team totals, next goal). Our per-market records:

| market | settled, priced | ROI |
|---|---|---|
| goals | 1,625 | −0.8 % |
| corners | **152** | −0.5 % |
| result | 665 | −3.3 % |
| cards | **37** | −9.4 % |

152 bets cannot prove a 0.5 % edge; the confidence interval spans zero by a mile. So our small-sample "best" markets
are not evidence of skill, they are the least-tested ones. That is why caps and lanes exist and should stay.

**Reachable:** only with time — the fix is *not* more markets, it is fewer, held honestly until the samples grow.

## 5. They never pay the margin, and they can hedge

We pay ~5 points of hold on every price. They collect it. They also balance liability across outcomes; we take a
single side and carry the variance. This is a structural gap that no modelling fixes, which is precisely why the
2026-10-27 rules took the two actions available to us: **nothing under 1.16** (where the hold cannot be overcome) and
**a 0.95 × fair price check** (a pick priced below our own fair estimate is a bet on the bookmaker being wrong about
us, and is demoted to the watchlist).

## 6. What we have that they don't

Worth stating, because it shapes strategy:

- **no margin and no limits** — we can take any price they offer, however small the stake;
- **no obligation to publish** — a bookmaker must price every match; we can simply not bet. The strongest "edge"
  available to us is refusing to play when the price is short;
- **honest, published measurement** — every pick is recorded with `p_model`, `p_sb` and `publication`-time odds, and
  graded; most tipsters never do the first part;
- **niche coverage** — small leagues where a trader's attention (and therefore the price quality) is thinner. Our
  African and lower-division coverage is a real information asymmetry *if* we can price it better than a bored
  trader — which brings us back to point 1: shots, not goals.

---

## What I would do next, in order

1. **Price history + CLV (1–2 days, no model risk).** Snapshot every published pick's price each run, report closing
   line value. This tells us whether the current picks are *beating the close* — the fastest honest read on edge.
2. **Shots-on-target study (offline, ~a week of analysis).** Does an `att`/`dfc` rating informed by shots on target
   (and xG where published) beat the goals-only version on Brier, log-loss **and** CLV over the archive? If it does
   not, we do not ship it, and we have learned the most important thing in this document.
3. **Confirmed-XI delta (bounded, measured).** Only after 2, and only with a cap and a record in the detail file.
4. **Nothing else.** No new markets, no accumulators, no "AI picks". The review's lesson was that we were already
   paying for the illusion of edge; adding surface area makes that worse.

## The one-line answer

They are not missing a trick we can copy. They have better inputs (shots/xG, team news), a live view of the whole
market, and a sample size we will never reach — and they charge us 5 points to find out. The two things we can
actually take from them are **pricing on underlying performance instead of goals** (we already store the data) and
**judging ourselves against the closing price instead of the result** (we already publish every 30 minutes). Both are
measurements before they are changes.
