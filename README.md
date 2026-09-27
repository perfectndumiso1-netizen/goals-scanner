# ⚽ PlayReport

Automatic football analysis that runs **every 30 minutes** on GitHub Actions and publishes to the PlayReport
Android app and Telegram — no servers, no API keys, and it runs while your phone is in your pocket.

* **Coverage** — every competition on the public live feed, worldwide (including women's and youth leagues),
  priced by Sportybet South Africa; the 22 main European leagues additionally get corners, cards and referee models.
* **Goals shortlists** — Over 1.5, Over 2.5, Both Teams To Score, from a backtested and calibrated model.
* **Safest bets** — singles at ≥ 70 % on *both* the model and the de-margined Sportybet price, price ≥ 1.30, in the
  goals / BTTS / team-goals / corners / cards markets. New ones are announced immediately (Telegram + app).
* **⭐ Bets of the day** — five singles picked at 07:00 from the safest bets, graded separately.
* **Trends, head-to-head and home/away form** on every match page; live scores, line-ups and match statistics for
  every match in play; squad values (Transfermarkt) for the main leagues.
* **Bet slip & tickets** in the app — build a multiple from priced selections, lock it, and PlayReport grades it from
  the scores and match statistics (private record on the phone).
* **Results archive** — every finished match on the live feed is kept with half-time score, corners, cards, shots and
  possession (`data/ls/` on the data branch), feeding the corners / cards models for every league over time.
* **Delivery** — full report (Markdown + PDF) at 07:00 / 12:00 / 17:00 SAST on Telegram; app data on the `data`
  branch (`data/app/latest.json`, per-match files, 60-day history); a weekly performance digest on Mondays.

The code lives on `main`; all generated state (reports, ledgers, app data, the Livescore archive) lives on the
orphan `data` branch, which is force-pushed by every run so the history stays small.

Statistical information, not betting advice. 18+.
