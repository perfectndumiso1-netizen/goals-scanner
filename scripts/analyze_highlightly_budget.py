#!/usr/bin/env python3
"""Offline request-cost assessment. No network, credentials, state or publishing.

All match counts/concurrency/read counts are planning inputs, not live evidence.
A planning margin is hypothetical headroom, NOT a production quota reservation.
Run: python scripts/analyze_highlightly_budget.py --rows 868 --remaining 90
"""
import argparse
import json


def integer(name, value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in [{minimum}, {maximum}]')
    return value


def ceiling_divide(value, divisor):
    return (value + divisor - 1) // divisor


def assess(rows=868, remaining=90, poll_minutes=20, window_minutes=960,
           catalog_scans=2, planning_margin=10, reads_per_match=8,
           details_per_bulk=2, targeted_per_cycle=2):
    """Compare demand, not a scheduler or promise of match/event completeness.

    The half-open window counts starts at 08:00, 08:20, ... 23:40, not 24:00.
    Per-match forecasts include baseline/terminal reads in the supplied count;
    extra time, suspension, failures and retries may require more.
    """
    for name, value, minimum, maximum in (
        ('rows', rows, 0, 100000), ('remaining', remaining, 0, 100),
        ('poll_minutes', poll_minutes, 1, 1440), ('window_minutes', window_minutes, 1, 1440),
        ('catalog_scans', catalog_scans, 1, 24), ('planning_margin', planning_margin, 0, 100),
        ('reads_per_match', reads_per_match, 1, 100), ('details_per_bulk', details_per_bulk, 0, 1000),
        ('targeted_per_cycle', targeted_per_cycle, 1, 1000),
    ):
        integer(name, value, minimum, maximum)
    pages = max(1, ceiling_divide(rows, 100))  # An empty catalog still costs a query.
    cycles = ceiling_divide(window_minutes, poll_minutes)
    catalog_requests = pages * catalog_scans
    live_budget = max(0, remaining - planning_margin - catalog_requests)
    cases = []
    for matches in (1, 2, 7, 8, 12):
        detail_requests = matches * reads_per_match
        planned_total = catalog_requests + detail_requests + planning_margin
        cases.append({'selected_matches': matches, 'reads_per_match': reads_per_match,
                      'catalog_requests': catalog_requests, 'detail_requests': detail_requests,
                      'planned_total_including_margin': planned_total,
                      'fits_input_balance': planned_total <= remaining})
    revisit = []
    for concurrent in (1, 2, 5, 8, 12, 20):
        # Conditional round-robin bound only if every cycle can afford its slots.
        revisit.append({'concurrent_matches': concurrent,
                        'minutes_per_round_if_funded': ceiling_divide(concurrent, targeted_per_cycle) * poll_minutes,
                        'all_matches_every_cycle_total_including_margin': catalog_requests + concurrent * cycles + planning_margin})
    return {
        'mode': 'offline_hypothetical_assessment', 'network_requests_made': 0,
        'assumptions': {'rows': rows, 'remaining_input_not_live_balance': remaining,
                        'window_minutes': window_minutes, 'poll_minutes': poll_minutes,
                        'catalog_scans': catalog_scans, 'planning_margin': planning_margin,
                        'reads_per_match': reads_per_match, 'targeted_per_cycle': targeted_per_cycle},
        'pages_per_catalog': pages, 'cycles_in_window': cycles,
        'current_bulk_list_requests': pages * cycles,
        'current_bulk_with_detail_ceiling': (pages + details_per_bulk) * cycles,
        'cached_catalog_requests': catalog_requests,
        'catalog_and_margin_affordable': catalog_requests + planning_margin <= remaining,
        'remaining_for_targeted_reads_after_margin': live_budget,
        'aggregate_matches_at_assumed_reads_each': live_budget // reads_per_match,
        'aggregate_capacity_is_not_a_cadence_guarantee': True,
        'selected_match_scenarios': cases,
        'concurrency_scenarios': revisit,
        'warnings': [
            'No live-only or multi-match batch filter was established by the reviewed docs.',
            'Cached kickoff metadata is not a fresh score or proof of kickoff/full-time.',
            'Catalog changes between scans can be missed until the next complete scan.',
            'Per-match assumptions do not guarantee full-time, every red card, or extra-time coverage.',
            'Concurrency, failures, quota changes and other consumers can defeat the aggregate estimate.',
            'No production configuration or account usage is changed by this calculator.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=868)
    parser.add_argument('--remaining', type=int, default=90)
    parser.add_argument('--poll-minutes', type=int, default=20)
    parser.add_argument('--catalog-scans', type=int, default=2)
    parser.add_argument('--planning-margin', type=int, default=10)
    parser.add_argument('--reads-per-match', type=int, default=8)
    args = parser.parse_args(argv)
    try:
        result = assess(**vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
