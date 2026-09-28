# ⚽ PlayReport

Automatic football analysis that runs **every 30 minutes** on GitHub Actions and publishes to the PlayReport
Android app and Telegram — no servers, no API keys, and it runs while your phone is in your pocket.

* **Coverage** — every competition on the public live feed, worldwide (including women's and youth leagues),
  priced by Sportybet South Africa; the 22 main European leagues additionally get corners, cards and referee models.
* **Data-first model** — every probability comes from football data only (goals, form, venue, league baseline →
  Dixon-Coles score matrix); bookmaker prices are a *separate comparison layer* (implied %, difference, EV, market xG)
  and never feed the model. Every statistic carries its sample size (Very small 1–4 … Very strong 40+), every match
  has a transparent data-quality assessment, the raw matches used, extreme results flagged and the model's own
  numbers ("why 1.35 goals?") in the app's **Data** tab and in `python audit.py HOME AWAY`. Missing data is N/A, never 0.
* **Goals shortlists** — Over 1.5, Over 2.5, Both Teams To Score, from the backtested and calibrated model.
* **High-probability selections** — singles with model probability ≥ 70 % (the de-margined Sportybet price must not
  contradict it), price ≥ 1.30, in the goals / BTTS / team-goals / corners / cards markets. New ones are announced
  immediately (Telegram + app). Nothing is ever labelled "safe" or "guaranteed".
* **⭐ Bets of the day** — grouped card, strong on Over 1.5 & team goals; 1X2 / BTTS / Over 2.5 only with strong supporting form; one market per match; graded separately.
* **Trends, head-to-head and home/away form** on every match page; live scores, line-ups and match statistics for
  every match in play; squad values (Transfermarkt) for the main leagues.
* **Bet slip & tickets** in the app — build a multiple from priced selections, lock it, and PlayReport grades it from
  the scores and match statistics (private record on the phone).
* **Results archive** — every finished match on the live feed is kept with half-time score, corners, cards, shots and
  possession (`data/ls/` on the data branch), feeding the corners / cards models for every league over time.
* **Checked before publishing** — every run exports the app data to a staging directory and `verify.py` checks it
  (format, probabilities, prices, selection rules, day-card sections, detail files, evidence layer, no market
  contamination of model probabilities, ledger integrity) before it is
  promoted; a failed check keeps the previous publication and reports the problem on Telegram.
* **Season backfill** — up to two earlier seasons of every covered competition are archived from Livescore once,
  so head-to-head, form and league pages are complete outside football-data's leagues.
* **Delivery** — full report (Markdown + PDF) at 07:00 / 12:00 / 17:00 SAST on Telegram; app data on the `data`
  branch (`data/app/latest.json`, per-match files, 60-day history); a weekly performance digest on Mondays.

The code lives on `main`; all generated state (reports, ledgers, app data, the Livescore archive) lives on the
orphan `data` branch, which is force-pushed by every run so the history stays small.

Statistical information, not betting advice. 18+.
