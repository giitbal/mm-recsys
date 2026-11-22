"""Fit observable targets from local train logs; keep raw records outside Git."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.common.artifacts import file_hash, write_json
from src.external_data.io import load_spec
from src.external_data.hm_prepare import simulator_category
from src.external_data.expansion_retail import observed_pairs, fit, predict, STATES
from src.external_data.realism_metrics import price_stats, purchase_stats, session_stats


def plan() -> tuple[dict, Path, Path]:
    spec = yaml.safe_load(Path('config/external_realism.yaml').read_text())
    work, output = Path(spec['work_dir']), Path(spec['results_dir'])
    work.mkdir(parents=True, exist_ok=True); output.mkdir(parents=True, exist_ok=True)
    marker = work / 'plan.json'
    if marker.exists() and json.loads(marker.read_text()) != spec:
        raise ValueError('changed plan; use a new experiment version')
    write_json(marker, spec)
    return spec, work, output


def prepare() -> None:
    spec, work, output = plan()
    if (output / 'targets.json').exists():
        audit = json.loads((output / 'inputs.json').read_text())
        if not all(file_hash(Path(p)) == h for p, h in audit['cache_hashes'].items()):
            raise ValueError('modified prepared reference cache')
        return
    source = Path(spec['source_work'])
    source_results = Path(spec['source_results'] if 'source_results' in spec
                          else load_spec('config/external_data.yaml')['results_dir'])
    hm_old = json.loads((source_results / 'hm_data.json').read_text())
    retail_old = json.loads((source_results / 'retailrocket.json').read_text())
    paths = {source / 'hm_raw' / n: hm_old['source_members'][n]['sha256'] for n in ['articles.csv', 'transactions_train.csv']}
    paths[source / 'retailrocket_raw/events.csv'] = retail_old['source_members']['events.csv']['sha256']
    for p, expected in paths.items():
        if file_hash(p) != expected:
            raise ValueError(f'changed source: {p}')
    users_path = Path(spec['source_expansion']) / 'hm_data/users.json'
    ids = json.loads(users_path.read_text())
    articles = pd.read_csv(source / 'hm_raw/articles.csv', dtype={'article_id': str})
    categories = pd.Series(articles.apply(simulator_category, axis=1).to_numpy(), index=articles.article_id)
    windows = {}
    for split in ['train', 'valid', 'test']:
        end = pd.Timestamp(hm_old['boundaries'][split]['end']) + pd.Timedelta(nanoseconds=1)
        start = end - pd.Timedelta(days=spec['purchase_window_days'])
        if start < pd.Timestamp(hm_old['boundaries'][split]['start']):
            raise ValueError('requested H&M window crosses split boundary')
        windows[split] = (start, end)
    chunks: dict[str, list] = {k: [] for k in windows}
    selected: dict[str, list] = {k: [] for k in windows}
    for i, chunk in enumerate(pd.read_csv(source / 'hm_raw/transactions_train.csv',
            usecols=['t_dat', 'customer_id', 'article_id', 'price'], dtype={'customer_id': str, 'article_id': str}, chunksize=500000)):
        for split, (start, end) in windows.items():
            local = chunk[(chunk.t_dat >= str(start.date())) & (chunk.t_dat < str(end.date()))].copy()
            if local.empty: continue
            local['category'] = local.article_id.map(categories)
            chunks[split].append(local[['category', 'price']])
            local = local[local.customer_id.isin(ids)].rename(columns={'customer_id': 'user_id', 'article_id': 'product_id'})
            local['timestamp'] = pd.to_datetime(local.pop('t_dat'), utc=True)
            selected[split].append(local)
        if i % 10 == 0: print('H&M source chunks', i + 1, flush=True)
    targets = {}
    for split, (start, end) in windows.items():
        prices = pd.concat(chunks[split], ignore_index=True)
        purchases = pd.concat(selected[split], ignore_index=True)
        purchases.to_parquet(work / f'hm_{split}.parquet', index=False)
        prices.to_parquet(work / f'prices_{split}.parquet', index=False)
        targets[split] = dict(price=price_stats(prices), purchase=purchase_stats(purchases, start, end, ids),
                              price_excluded_unmapped=int(prices.category.isna().sum()))
    del chunks, selected, prices, purchases
    events = pd.read_csv(source / 'retailrocket_raw/events.csv', usecols=['timestamp', 'visitorid', 'event', 'itemid'])
    events.timestamp = pd.to_datetime(events.timestamp, unit='ms', utc=True)
    events.event = events.event.map({'view': 'view', 'addtocart': 'cart', 'transaction': 'purchase'})
    events['row_id'] = np.arange(len(events))
    events = events.sort_values(['visitorid', 'timestamp', 'row_id'], kind='stable')
    previous = events.groupby('visitorid').cumcount() - events.groupby(['visitorid', 'timestamp']).cumcount()
    events['activity'] = np.digitize(previous, spec['activity_thresholds'])
    ends = [pd.Timestamp(retail_old['split_boundaries'][k]) + pd.Timedelta(milliseconds=1) for k in ['train_end', 'valid_end']]
    ends.append(events.timestamp.max() + pd.Timedelta(milliseconds=1))
    starts = [events.timestamp.min(), *ends[:2]]
    for split, lower, end in zip(['train', 'valid', 'test'], starts, ends):
        start = end - pd.Timedelta(days=spec['session_window_days'])
        if start < lower: raise ValueError('Retailrocket window crosses boundary')
        window = events[(events.timestamp >= start) & (events.timestamp < end)]
        window.to_parquet(work / f'retail_{split}.parquet', index=False)
        targets[split]['session'] = session_stats(window.rename(columns={'visitorid': 'user_id'}), start, end, spec['session_seconds'])
    train = events[events.timestamp < ends[0]]
    pairs = observed_pairs(train, ends[0] - pd.Timedelta(milliseconds=1), spec['session_seconds'])
    counts = fit(pairs, 'activity')
    total = pairs.groupby(['event', 'next']).size()
    matrix = np.array([[total.get((s, d), 0) + 1 for d in STATES] for s in STATES[:3]], float)
    matrix /= matrix.sum(axis=1, keepdims=True)
    query = pd.DataFrame([(a, s) for a in range(3) for s in STATES[:3]], columns=['activity', 'event'])
    conditional = predict(query, 'activity', counts, matrix, spec['activity_alpha']).reshape(3, 3, 4)
    ordered = train.sort_values(['visitorid', 'timestamp', 'row_id'])
    gaps = ordered.groupby('visitorid').timestamp.diff().dt.total_seconds()
    tied = ordered.duplicated(['visitorid', 'timestamp'], keep=False)
    good = gaps.gt(0) & gaps.le(spec['session_seconds']) & ~tied & ~tied.groupby(ordered.visitorid).shift(1, fill_value=False)
    window_train = pd.read_parquet(work / 'retail_train.parquet')
    frequencies = window_train.groupby('visitorid').size().to_numpy()
    # Quantile tables are aggregate parameters, not copies of user trajectories.
    profile = dict(activity_quantiles=np.quantile(frequencies, np.linspace(0, 1, 101)).tolist(),
                   within_gap_quantiles=np.quantile(gaps[good], np.linspace(.005, .995, 101)).tolist(),
                   activity_thresholds=spec['activity_thresholds'], transitions=conditional.tolist(),
                   global_transitions=matrix.tolist(), session_seconds=spec['session_seconds'],
                   fit_scope='Retailrocket train only; no category/persona mapping; prior observable event counts')
    write_json(work / 'behavior_profile.json', profile)
    write_json(output / 'behavior_profile.json', profile)
    write_json(output / 'targets.json', targets)
    write_json(output / 'inputs.json', dict(source_hashes={str(p): h for p, h in paths.items()},
        cohort_hash=file_hash(users_path), cohort_users=len(ids),
        cache_hashes={str(p): file_hash(p) for p in work.glob('*.parquet')},
        policy='Real targets use disjoint trailing 28-day purchase / 14-day session windows; 100k preselected H&M users, all-source mapped transaction prices; active-only Retailrocket visitor roster',
        limitations=['Previously inspected real test is exploratory, not fresh holdout',
                    'H&M has dates, not click-session timestamps; purchase duplicates collapse per user-item-day',
                    'No causal elasticity, release dates, persona membership or cross-brand loyalty inference']))
    print('Prepared real-world targets and train-only behavior profile', flush=True)


if __name__ == '__main__':
    prepare()
