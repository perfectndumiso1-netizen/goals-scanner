"""Referee historical card & foul context (display-only, never alters goal rates or probabilities).

When a fixture carries an appointed referee name and the historical results archive contains at least
5 matches officiated by that referee with card statistics, we emit a factual provider-tier context note
with average bookings per match (and fouls per match when available). If fewer than 5 tracked matches
exist, an explicit N/A gap fact is recorded instead of guessing.
"""
from __future__ import annotations

from datetime import datetime
import pandas as pd

from . import facts as F

MIN_REF_MATCHES = 5


def facts_for(results: pd.DataFrame | None, fx: dict, now: datetime) -> list[F.Fact]:
    ref = str(fx.get("referee") or fx.get("ref") or "").strip()
    if not ref or ref.upper() == "N/A":
        return []
    if results is None or results.empty or "referee" not in results.columns or "hy" not in results.columns:
        return [
            F.make_fact(
                "referee",
                ref,
                f"N/A — referee {ref} appointed, no historical card archive available",
                "historical results archive",
                now,
                kind="referee_unavailable",
                value={"referee": ref, "n": 0},
            )
        ]

    sub = results[results["referee"].astype(str).str.strip().str.lower() == ref.lower()].copy()
    if not sub.empty and "date" in sub.columns:
        ko = F.as_aware(fx.get("kickoff"), now)
        if ko is not None:
            cut = pd.Timestamp(ko.date())
            sub = sub[pd.to_datetime(sub["date"], errors="coerce") < cut]

    hy = pd.to_numeric(sub.get("hy"), errors="coerce")
    ay = pd.to_numeric(sub.get("ay"), errors="coerce")
    hr = pd.to_numeric(sub.get("hr", 0), errors="coerce").fillna(0.0)
    ar = pd.to_numeric(sub.get("ar", 0), errors="coerce").fillna(0.0)
    valid = hy.notna() & ay.notna()
    n = int(valid.sum())
    if n < MIN_REF_MATCHES:
        return [
            F.make_fact(
                "referee",
                ref,
                f"N/A — referee {ref}: fewer than {MIN_REF_MATCHES} tracked matches with card stats ({n})",
                "historical results archive",
                now,
                kind="referee_unavailable",
                value={"referee": ref, "n": n},
            )
        ]

    cards = (hy[valid] + ay[valid] + hr[valid] + ar[valid]).astype(float)
    avg_cards = round(float(cards.mean()), 2)
    o35_rate = round(float((cards > 3.5).mean()), 3)
    val = {"referee": ref, "n": n, "cards_pg": avg_cards, "o35_cards_rate": o35_rate}
    foul_str = ""
    if "hf" in sub.columns and "af" in sub.columns:
        hf = pd.to_numeric(sub.get("hf"), errors="coerce")
        af = pd.to_numeric(sub.get("af"), errors="coerce")
        fvalid = valid & hf.notna() & af.notna()
        if int(fvalid.sum()) >= MIN_REF_MATCHES:
            avg_fouls = round(float((hf[fvalid] + af[fvalid]).mean()), 1)
            val["fouls_pg"] = avg_fouls
            foul_str = f", {avg_fouls:.1f} fouls/game"

    text = f"Referee {ref}: {avg_cards:.2f} cards/game ({round(o35_rate * 100)}% over 3.5 cards{foul_str}, n={n})"
    return [
        F.make_fact(
            "referee",
            ref,
            text,
            "historical results archive",
            now,
            confidence="provider",
            verified=False,
            kind="referee_cards",
            value=val,
        )
    ]
