"""Spoken-English helpers: numbers, scores, times and names the way a presenter says them."""
from __future__ import annotations

import spoken as sp


def test_numbers_and_ordinals_become_words():
    assert [sp.words(n) for n in (0, 7, 13, 20, 45, 101)] == ["zero", "seven", "thirteen", "twenty", "forty-five", "one hundred and one"]
    assert [sp.ordinal(n) for n in (1, 2, 3, 8, 12, 17, 21, 30, 42)] == [
        "first", "second", "third", "eighth", "twelfth", "seventeenth", "twenty-first", "thirtieth", "forty-second"]


def test_scores_are_football_scores():
    assert sp.score(3, 2) == "three-two" and sp.score(2, 3) == "three-two"          # winner's goals first
    assert sp.score(2, 0) == "two-nil" and sp.score(0, 6) == "six-nil"
    assert sp.score(1, 1) == "one-all" and sp.score(0, 0) == "nil-nil"


def test_per_game_rates_sound_like_a_person():
    assert sp.per_game(1.44) == "about one and a half"
    assert sp.per_game(1.75) == "getting on for two"
    assert sp.per_game(2.11) == "just over two"
    assert sp.per_game(0.83) == "just under one"
    assert sp.per_game(3.5) == "three and a half"
    assert sp.per_game(4.58) == "four and a half"
    assert sp.per_game(None) == ""
    # never a decimal or a digit
    assert not any(ch.isdigit() for x in (0.3, 0.9, 1.2, 1.9, 2.4, 2.9, 3.2, 4.0, 6.0) for ch in sp.per_game(x))


def test_shares_are_spoken_fractions_not_percentages():
    assert sp.rate(0.84) == "better than four in five"
    assert sp.rate(0.96) == "nine in ten"
    assert sp.rate(0.5) == "about half"
    assert "%" not in "".join(sp.rate(x) for x in (0.2, 0.5, 0.7, 0.8, 0.9, 1.0))
    assert sp.of_last(5, 5) == "all of their last five"
    assert sp.of_last(10, 10) == "every one of their last ten"
    assert sp.of_last(4, 5) == "four of their last five"


def test_kickoff_times_are_said_not_read():
    assert sp.kickoff("20:45") == "at quarter to nine tonight"
    assert sp.kickoff("21:00") == "at nine tonight"
    assert sp.kickoff("15:30") == "at half past three this afternoon"
    assert sp.kickoff("16:15") == "at quarter past four this afternoon"
    assert sp.kickoff("11:00") == "at eleven this morning"
    assert sp.clock("19:35") == "twenty-five to eight"
    assert sp.all_evening(["20:45", "21:00"]) and not sp.all_evening(["15:30", "21:00"])


def test_club_names_are_said_the_way_commentators_say_them():
    said = {n: sp.team(n) for n in ("FC Cologne", "Kristiansund BK", "Sarpsborg 08", "Bodoe/Glimt", "St. Louis City", "St Pauli",
                                    "SC Heerenveen", "Eintracht Frankfurt", "Paris Saint-Germain", "Willem II", "Schalke 04",
                                    "Deportivo A Coruna", "Bîrligea")}
    assert said["FC Cologne"] == "Cologne" and said["Kristiansund BK"] == "Kristiansund" and said["Sarpsborg 08"] == "Sarpsborg"
    assert said["Bodoe/Glimt"] == "Bodo Glimt" and said["St. Louis City"] == "Saint Louis City" and said["St Pauli"] == "Saint Pauli"
    assert said["SC Heerenveen"] == "Heerenveen" and said["Eintracht Frankfurt"] == "Frankfurt" and said["Paris Saint-Germain"] == "PSG"
    assert said["Willem II"] == "Willem Two" and said["Schalke 04"] == "Schalke" and said["Deportivo A Coruna"] == "Deportivo La Coruna"
    assert said["Bîrligea"] == "Birligea"                                                    # accents never trip the voice


def test_name_lists_trim_long_injury_lists():
    assert sp.names(["Aubameyang", "Marc Casadó", "Eddahchouri"]) == "Aubameyang, Marc Casado and Eddahchouri"
    assert sp.names(["A", "B", "C", "D", "E"]) == "A, B, C and two others"
    assert sp.names(["A", "B", "C", "D"]) == "A, B, C and one other"


def test_betting_lines_are_spoken_in_words():
    assert sp.half_line("Over 1.5 goals") == "Over one and a half goals"
    assert sp.half_line("over 9.5 corners") == "over nine and a half corners"


def test_chooser_is_reproducible_and_never_repeats_back_to_back():
    a, b = sp.Chooser(sp.seed_for("2026-10-17", "x")), sp.Chooser(sp.seed_for("2026-10-17", "x"))
    opts = ["one", "two", "three"]
    seq_a = [a.pick("k", opts) for _ in range(12)]
    assert seq_a == [b.pick("k", opts) for _ in range(12)]
    assert all(x != y for x, y in zip(seq_a, seq_a[1:]))
    assert sp.seed_for("2026-10-17", "x") != sp.seed_for("2026-10-18", "x")
