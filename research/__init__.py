"""The live-research / context layer (Phase A: collect, store, display).

WHAT THIS PACKAGE IS
--------------------
A structured, bounded, auditable layer that records *verified current football information* about a fixture —
availability, line-ups, team news, motivation/match context, fatigue/scheduling and weather — and (only when a
rule is explicitly enabled) translates a small number of those facts into a bounded adjustment of the goals
expectation **before** the final probability is published.

HOW IT RELATES TO THE MODEL
---------------------------
* The statistical engine is untouched.  `scanner.analyse()` still produces `p_model` from the Dixon-Coles score
  matrix exactly as before; that value is the **base probability** and is always published alongside the final one.
* An adjustment is never applied to probabilities directly.  It scales the goal rates (lambda) and the *existing*
  `score_matrix()` / `probs_from_matrix()` are re-run, so every market stays internally consistent.
* Bookmaker / Sportybet odds are never an input here.  There is no odds field anywhere in this package.

HARD RULES (enforced in code, see `context.py` and the unit tests)
------------------------------------------------------------------
1. Every fact carries a source, a retrieval timestamp, an information timestamp and a confidence.  Unknown is
   "N/A" — never an estimate, never a substitute team or player.
2. Facts are separated from model interpretation (`Rule` objects carry the interpretation, facts never do).
3. Weak, stale or contradictory evidence means **adjustment 0**, never a guess.
4. Adjustments are rule-based, per-category capped, and the total is capped by `RES_MAX_ADJ_PP` /
   `RES_MAX_LAMBDA_PCT`.
5. Research quality (HIGH/MEDIUM/LOW/INSUFFICIENT) is reported per fixture and never feeds the probability.
6. Confirmed and predicted line-ups are never conflated: only line-ups actually published by the feed are used,
   and they are marked as such.  There is no predicted-line-up source in this system.

PHASE GATE
----------
`RESEARCH=1` (default) collects and displays facts; `RESEARCH_ADJUST=0` (default) guarantees the published
probability is byte-identical to the statistical model.  Setting `RESEARCH_ADJUST=1` alone changes nothing —
each category also starts with a zero weight (`RES_*_WEIGHT=0.0`) until the backtest in Phase B justifies it.
"""
from __future__ import annotations

from .facts import Fact, ResearchRecord, freshness, grade_quality, iso, make_fact  # noqa: F401
from .context import Config, Engine  # noqa: F401

__all__ = ["Config", "Engine", "Fact", "ResearchRecord", "freshness", "grade_quality", "iso", "make_fact"]
