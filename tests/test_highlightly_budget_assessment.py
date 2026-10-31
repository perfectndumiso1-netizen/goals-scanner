"""Cost arithmetic only. These tests do not call a score provider or Facebook."""
import json
import pytest
from scripts.analyze_highlightly_budget import assess, main


def test_observed_row_count_is_an_input_not_live_traffic():
    result = assess()
    assert result['network_requests_made'] == 0
    assert result['mode'] == 'offline_hypothetical_assessment'
    assert result['pages_per_catalog'] == 9
    assert result['cycles_in_window'] == 48
    assert result['current_bulk_list_requests'] == 432
    assert result['current_bulk_with_detail_ceiling'] == 528
    assert result['cached_catalog_requests'] == 18
    assert result['remaining_for_targeted_reads_after_margin'] == 62
    assert result['aggregate_matches_at_assumed_reads_each'] == 7
    assert result['aggregate_capacity_is_not_a_cadence_guarantee'] is True


def test_seven_match_plan_fits_90_but_eight_needs_fresh_day_allowance():
    current = assess(remaining=90)
    fresh = assess(remaining=100)
    seven = next(r for r in current['selected_match_scenarios'] if r['selected_matches'] == 7)
    eight = next(r for r in current['selected_match_scenarios'] if r['selected_matches'] == 8)
    assert seven['planned_total_including_margin'] == 84 and seven['fits_input_balance']
    assert eight['planned_total_including_margin'] == 92 and not eight['fits_input_balance']
    assert next(r for r in fresh['selected_match_scenarios'] if r['selected_matches'] == 8)['fits_input_balance']
    assert fresh['aggregate_matches_at_assumed_reads_each'] == 9


def test_concurrency_is_separate_from_daily_aggregate_budget():
    result = assess()
    eight = next(r for r in result['concurrency_scenarios'] if r['concurrent_matches'] == 8)
    assert eight['minutes_per_round_if_funded'] == 80
    one = result['concurrency_scenarios'][0]
    assert one['all_matches_every_cycle_total_including_margin'] == 76
    two = result['concurrency_scenarios'][1]
    assert two['all_matches_every_cycle_total_including_margin'] == 124


@pytest.mark.parametrize('rows,pages', [(0,1),(100,1),(101,2),(284,3),(868,9)])
def test_empty_and_paginated_catalog_costs(rows,pages):
    assert assess(rows=rows)['pages_per_catalog'] == pages


@pytest.mark.parametrize('balance', [0,5,10,27])
def test_low_balance_is_not_overbooked_or_reset(balance):
    result = assess(remaining=balance)
    assert result['remaining_for_targeted_reads_after_margin'] == 0
    assert result['aggregate_matches_at_assumed_reads_each'] == 0
    assert not result['catalog_and_margin_affordable']


@pytest.mark.parametrize('kwargs', [
    {'rows':True}, {'rows':-1}, {'remaining':101}, {'remaining':-1},
    {'poll_minutes':0}, {'window_minutes':1441}, {'catalog_scans':0},
    {'planning_margin':-1}, {'reads_per_match':0}, {'targeted_per_cycle':0},
])
def test_invalid_assumptions_are_rejected(kwargs):
    with pytest.raises(ValueError):assess(**kwargs)


def test_half_open_window_uses_no_midnight_slot():
    assert assess(poll_minutes=60)['cycles_in_window'] == 16
    assert assess(poll_minutes=120)['cycles_in_window'] == 8
    assert assess(poll_minutes=23)['cycles_in_window'] == 42


def test_more_extra_time_reads_reduce_the_plannable_match_count():
    assert assess(reads_per_match=16)['aggregate_matches_at_assumed_reads_each'] == 3


def test_cli_is_reproducible_and_labels_hypothetical_input(capsys):
    assert main(['--rows','868','--remaining','90']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['assumptions']['remaining_input_not_live_balance'] == 90
    assert report['network_requests_made'] == 0


def test_cli_rejects_invalid_input():
    with pytest.raises(SystemExit) as error:main(['--remaining','200'])
    assert error.value.code == 2
