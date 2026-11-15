"""Train-only session transitions; no fabricated search or exposure events."""
from __future__ import annotations

import pandas as pd

from src.common.artifacts import write_json
from src.external_data.io import extract_member, paths

STATES = ('view', 'cart', 'purchase')


def transition_counts(events: pd.DataFrame, end: pd.Timestamp, session_seconds: int) -> tuple[dict, dict]:
    ordered = events.sort_values(['visitorid', 'timestamp', 'row_id'], kind='stable').copy()
    grouped = ordered.groupby('visitorid', sort=False)
    following_time = grouped.timestamp.shift(-1)
    following_state = grouped.event.shift(-1)
    gap = following_time - ordered.timestamp
    window = pd.Timedelta(seconds=session_seconds)
    tied = ordered.duplicated(['visitorid', 'timestamp'], keep=False)
    following_tied = tied.groupby(ordered.visitorid).shift(-1, fill_value=False)
    linked = gap.gt(pd.Timedelta(0)) & gap.le(window) & ~tied & ~following_tied
    # A following event beyond the inactivity window establishes exit. At the right
    # boundary, an entire inactivity window must have elapsed before declaring exit.
    exited = (gap.gt(window) | following_time.isna()) & (ordered.timestamp + window <= end) & ~tied
    pairs = pd.DataFrame({'origin': ordered.event, 'destination': following_state})
    pairs.loc[exited, 'destination'] = 'exit'
    counts = pd.crosstab(pairs.loc[linked | exited, 'origin'], pairs.loc[linked | exited, 'destination'])
    matrix = {state: {dest: int(counts.loc[state, dest]) if state in counts.index and dest in counts else 0
                      for dest in (*STATES, 'exit')} for state in STATES}
    return matrix, dict(events=len(events), visitors=int(events.visitorid.nunique()),
        observed_transitions=int(linked.sum()), observed_exits=int(exited.sum()),
        ambiguous_same_timestamp_pairs=int(gap.eq(pd.Timedelta(0)).sum()),
        ambiguous_tied_event_rows=int(tied.sum()),
        right_censored_events=int((following_time.isna() & ~tied & (ordered.timestamp + window > end)).sum()))


def probabilities(counts: dict, smoothing: float) -> dict:
    result = {}
    for state, row in counts.items():
        denominator = sum(row.values()) + smoothing * len(row)
        if denominator <= 0: raise ValueError('unobserved transition row without smoothing')
        result[state] = {dest: (count + smoothing) / denominator for dest, count in row.items()}
    return result


def run(spec: dict) -> dict:
    source, work, results = paths(spec)
    raw = work / 'retailrocket_raw'
    sources = {}
    for name in ('events.csv', 'item_properties_part1.csv', 'item_properties_part2.csv'):
        sources[name] = extract_member(source / (spec['retailrocket']['events_archive'] if name == 'events.csv' else name + '.zip'), name, raw / name)
    events = pd.read_csv(raw / 'events.csv', usecols=['timestamp', 'visitorid', 'event', 'itemid'])
    if events.isna().any().any(): raise ValueError('missing Retailrocket event fields')
    events['event'] = events.event.map({'view': 'view', 'addtocart': 'cart', 'transaction': 'purchase'})
    if events.event.isna().any(): raise ValueError('unknown Retailrocket event')
    events['timestamp'] = pd.to_datetime(events.timestamp, unit='ms', utc=True)
    events['row_id'] = events.index
    ordered = events.sort_values(['timestamp', 'row_id'], kind='stable')
    a, b = [ordered.timestamp.iloc[int(len(ordered) * f)] for f in (.8, .9)]
    splits = {'train': ordered[ordered.timestamp <= a], 'valid': ordered[(ordered.timestamp > a) & (ordered.timestamp <= b)], 'test': ordered[ordered.timestamp > b]}
    counts, diagnostics = {}, {}
    for split, frame in splits.items():
        if frame.empty: raise ValueError('empty Retailrocket split')
        counts[split], diagnostics[split] = transition_counts(frame, frame.timestamp.max(), spec['retailrocket']['session_seconds'])
    fitted = probabilities(counts['train'], spec['retailrocket']['smoothing'])
    differences = {}
    for split in ('valid', 'test'):
        observed = probabilities(counts[split], 0)
        differences[split] = {state: sum(abs(observed[state][d] - fitted[state][d]) for d in fitted[state]) / 2 for state in STATES}
    properties = {}
    for name in ('item_properties_part1.csv', 'item_properties_part2.csv'):
        count, categories, available = 0, 0, 0
        for chunk in pd.read_csv(raw / name, dtype={'property': str, 'value': str}, chunksize=500000):
            if list(chunk.columns) != ['timestamp', 'itemid', 'property', 'value']:
                raise ValueError('invalid item properties schema')
            count += len(chunk); categories += int(chunk.property.eq('categoryid').sum()); available += int(chunk.property.eq('available').sum())
        properties[name] = dict(rows=count, category_records=categories, availability_records=available,
                                use='inventory only; global state transitions do not require item-property joins')
    report = dict(status='PASS', acceptance='UNMEASURED', source_members=sources, property_inventory=properties,
        counts=counts, diagnostics=diagnostics, fitted_transitions=fitted, heldout_total_variation=differences,
        split_boundaries={'train_end': str(a), 'valid_end': str(b)}, session_seconds=spec['retailrocket']['session_seconds'],
        smoothing=spec['retailrocket']['smoothing'], fit_scope='train only, user-level successive observable events',
        limitations=['same-timestamp pairs excluded as order is unknown', 'split-boundary unfinished sessions censored',
                    'no search logs, persona labels or unclicked impressions; search transitions remain synthetic assumptions'])
    write_json(results / 'retailrocket.json', report)
    return report
