"""H&M purchase data, a predeclared user cohort, and train-only calibration."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from src.common.artifacts import file_hash, fingerprint, write_json
from src.external_data.io import extract_member, paths


def day_boundaries(counts: dict[str, int]) -> tuple[str, str]:
    days = sorted(counts)
    cumulative = np.cumsum([counts[d] for d in days])
    a, b = [days[int(np.searchsorted(cumulative, cumulative[-1] * f))] for f in (.8, .9)]
    if a >= b or b >= days[-1]:
        raise ValueError('insufficient distinct days for temporal 8/1/1 split')
    return a, b


def simulator_category(row: pd.Series) -> str | None:
    # Only map categories represented in the existing synthetic catalog.
    kind, group = row.product_type_name, row.product_group_name
    if group == 'Shoes': return 'footwear'
    if group == 'Accessories': return 'accessories'
    if kind in ('Jacket', 'Coat', 'Blazer', 'Outdoor overall'): return 'outerwear'
    if kind in ('Trousers', 'Jeans', 'Shorts', 'Skirt'): return 'bottoms'
    if group == 'Garment Upper body': return 'tops'
    return None


def prepare(spec: dict) -> dict:
    source, work, results = paths(spec)
    raw, output = work / 'hm_raw', work / 'hm'
    if (output / 'split_manifest.json').exists():
        from src.recommendation.datasets import read_data
        read_data(output, 'test')
        return json.loads((results / 'hm_data.json').read_text())
    archive = source / spec['hm']['archive']
    sources = {name: extract_member(archive, name, raw / name)
               for name in ('articles.csv', 'customers.csv', 'transactions_train.csv', 'sample_submission.csv')}
    articles = pd.read_csv(raw / 'articles.csv', dtype={'article_id': str, 'product_code': str})
    customers = pd.read_csv(raw / 'customers.csv', usecols=['customer_id'], dtype=str)
    if articles.article_id.duplicated().any() or customers.customer_id.duplicated().any():
        raise ValueError('duplicate source IDs')
    ids = np.sort(customers.customer_id.to_numpy())
    rng = np.random.default_rng(spec['seed'])
    selected = set(rng.choice(ids, min(spec['hm']['user_limit'], len(ids)), replace=False))
    daily: Counter = Counter()
    first_seen: dict = {}
    picked = []
    offset = 0
    read = dict(chunksize=spec['hm']['chunk_rows'], dtype={'customer_id': str, 'article_id': str})
    for chunk in pd.read_csv(raw / 'transactions_train.csv', **read):
        if chunk[['t_dat', 'customer_id', 'article_id', 'price']].isna().any().any() or not np.isfinite(chunk.price).all() or (chunk.price < 0).any():
            raise ValueError('invalid H&M transaction')
        if not chunk.article_id.isin(articles.article_id).all():
            raise ValueError('orphan transaction product')
        daily.update(chunk.t_dat.value_counts().to_dict())
        for pid, day in chunk.groupby('article_id').t_dat.min().items():
            first_seen[pid] = min(first_seen.get(pid, day), day)
        subset = chunk[chunk.customer_id.isin(selected)].copy()
        subset['event_id'] = ['HM-E' + str(i) for i in subset.index]
        picked.append(subset)
        offset += len(chunk)
    a, b = day_boundaries(daily)
    counts = pd.Series(0., index=articles.article_id)
    prices = counts.copy()
    for chunk in pd.read_csv(raw / 'transactions_train.csv', **read):
        train = chunk[chunk.t_dat <= a]
        grouped = train.groupby('article_id').price.agg(['sum', 'count'])
        counts = counts.add(grouped['count'], fill_value=0)
        prices = prices.add(grouped['sum'], fill_value=0)
    mean_price = (prices / counts.replace(0, np.nan)).reindex(articles.article_id)
    fallback = float(prices.sum() / counts.sum())
    last_day = max(daily)
    products = pd.DataFrame(dict(product_id='HM-' + articles.article_id, name=articles.prod_name.fillna('unknown'),
        category_l1=articles.product_group_name, category_l2=articles.garment_group_name,
        category_l3=articles.product_type_name, brand='H&M', color=articles.colour_group_name,
        style=articles.graphical_appearance_name, attributes='{}',
        price=mean_price.fillna(fallback).to_numpy(), price_missing=mean_price.isna().to_numpy(),
        created_at=pd.to_datetime(articles.article_id.map(first_seen).fillna(last_day), utc=True),
        description_en=articles.detail_desc.fillna(articles.prod_name),
        image_path=articles.article_id.map(lambda pid: f'images/{pid[:3]}/{pid}.jpg')))
    # Never-observed products remain unavailable, rather than appearing on the last observed day.
    never_seen = ~articles.article_id.isin(first_seen)
    products.loc[never_seen, 'created_at'] = pd.Timestamp(last_day, tz='UTC') + pd.Timedelta(days=1)
    with ZipFile(archive) as z:
        names = set(z.namelist())
    image_present = products.image_path.isin(names)
    tx = pd.concat(picked, ignore_index=True)
    events = pd.DataFrame(dict(event_id=tx.event_id, user_id='HM-' + tx.customer_id,
        product_id='HM-' + tx.article_id, event_type='purchase', timestamp=pd.to_datetime(tx.t_dat, utc=True),
        session_id='HM-DAY-' + tx.customer_id + '-' + tx.t_dat, query=None, impression_id=None, position=None))
    users = pd.DataFrame({'user_id': ['HM-' + uid for uid in sorted(selected)]})
    users['signup_at'] = users.user_id.map(events.groupby('user_id').timestamp.min()).fillna(pd.Timestamp(last_day, tz='UTC') + pd.Timedelta(days=1))
    users['age_group'] = 'unknown'; users['gender'] = 'unknown'; users['persona'] = 'unobserved'
    # The downloaded customer demographics are a timeless snapshot; do not backdate them.
    splits = {'train': events[events.timestamp <= pd.Timestamp(a, tz='UTC')],
              'valid': events[(events.timestamp > pd.Timestamp(a, tz='UTC')) & (events.timestamp <= pd.Timestamp(b, tz='UTC'))],
              'test': events[events.timestamp > pd.Timestamp(b, tz='UTC')]}
    if any(frame.empty for frame in splits.values()): raise ValueError('empty H&M cohort split')
    (output / 'split').mkdir(parents=True, exist_ok=True)
    frames = {'products.parquet': products, 'users.parquet': users, **{f'split/{k}.parquet': v for k, v in splits.items()}}
    for name, frame in frames.items(): frame.to_parquet(output / name, index=False)
    # End-of-day cutoffs include the entire previous day under the existing strict '< cutoff' contract.
    ends = {'train': a, 'valid': b, 'test': last_day}
    boundaries = {k: {'start': str(v.timestamp.min()), 'end': str(pd.Timestamp(ends[k], tz='UTC') + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))}
                  for k, v in splits.items()}
    hashes = {name: file_hash(output / name) for name in frames}
    manifest = dict(generation_fingerprint=fingerprint(dict(sources=sources, seed=spec['seed'], users=sorted(selected), hashes=hashes)),
        generator_version='hm-adapter-v1', scale='external_cohort', seed=spec['seed'],
        file_hashes=hashes, boundaries=boundaries, counts=dict(products=len(products), users=len(users), events=len(events)),
        split_counts={k: len(v) for k, v in splits.items()}, cutoff_policy='fixed_origin', source_members=sources)
    mapped = articles.apply(simulator_category, axis=1)
    analysis = pd.DataFrame({'category': mapped, 'count': counts.reindex(articles.article_id).to_numpy(),
                             'price_sum': prices.reindex(articles.article_id).to_numpy()})
    grouped = analysis.dropna(subset=['category']).groupby('category')[['count', 'price_sum']].sum()
    calibration = dict(train_end=a, train_transactions=int(counts.sum()), mapped_train_transactions=int(grouped['count'].sum()),
        excluded_train_transactions=int(counts.sum() - grouped['count'].sum()),
        category_purchase_shares=(grouped['count'] / grouped['count'].sum()).to_dict(),
        relative_category_price=((grouped.price_sum / grouped['count']) / fallback).to_dict(),
        price_unit='H&M normalized price; relative category ratios only, no KRW conversion',
        fit_scope='all source transactions in train only; no valid/test outcomes',
        unidentified=['true registration dates', 'six persona membership', 'brand loyalty', 'causal price elasticity', 'impression CTR/CVR'])
    report = dict(status='PASS', acceptance='UNMEASURED', source_members=sources, total_source_transactions=offset,
        source_customers=len(customers), cohort=manifest['counts'], split_counts=manifest['split_counts'], boundaries=boundaries,
        cohort_policy='seed42 uniform sample from all customer IDs before observing outcomes; no activity/quality filtering',
        actual_source_split_counts={k: sum(n for d, n in daily.items() if (d <= a if k == 'train' else a < d <= b if k == 'valid' else d > b)) for k in splits},
        full_catalog=True, image_files=len([n for n in names if n.startswith('images/') and n.endswith('.jpg')]),
        products_with_images=int(image_present.sum()), products_without_images=int((~image_present).sum()),
        proxy_policy='created_at/signup_at = first observed purchase; daily session_id is not a click session; customer snapshot demographics unused',
        metadata_limitation='static articles snapshot; historical attribute availability cannot be verified; train-only mean price with train-global fallback',
        missing_train_prices=int(products.price_missing.sum()), calibration=calibration)
    write_json(results / 'hm_data.json', report)
    write_json(output / 'split_manifest.json', manifest)
    return report
