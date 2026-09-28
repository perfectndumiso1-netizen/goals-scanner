## What's new in PlayReport 1.5 — data-first engine
- Every probability now comes from football data only. Bookmaker prices are shown next to the model as a separate comparison (implied %, difference in points, EV) and never change a model probability.
- Model xG and Market xG are shown separately on every match page — never blended.
- New Data tab on every match: data quality (High / Medium / Low with the reasons), the sample behind each team (matches, competitions, season, home/away, friendlies), home/away splits as plain historical frequencies, extreme results flagged, the raw matches used, head-to-head evidence strength, the model's own numbers ("why 1.35 goals?") and automatic checks and warnings.
- Every statistic carries its sample size: Very small (1–4), Small (5–9), Moderate (10–19), Strong (20–39), Very strong (40+). Historical frequency ("scored in 9 of 10") is always labelled apart from model probability and market implied.
- Markets tab: Model / Market / Diff / Price · EV columns; corners and cards show LOW DATA CONFIDENCE when the sample is thin.
- "Safest bets" are now called high-probability selections — a 75% probability still loses one time in four. Each one shows its data quality.
- Model update validated on 52,000 matches: team strength is shrunk less than goal tempo, which improves home/away win, Over 1.5 and Over 2.5 accuracy (details in backtest/RESULTS.md).
- CSV downloads include the data-quality assessment, the raw matches used and the model/market comparison.
