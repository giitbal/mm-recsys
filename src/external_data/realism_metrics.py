"""Comparable observable statistics; no synthetic persona labels or hidden tastes."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

QUANTILES = [.1, .25, .5, .75, .9]


def quantiles(values: np.ndarray | pd.Series) -> list[float] | None:
    values = np.asarray(values, dtype=float)
    return np.quantile(values, QUANTILES).tolist() if len(values) else None


def activity_stats(counts: pd.Series) -> dict:
    values = counts.to_numpy(dtype=float)
    positive = values[values > 0]
    total = positive.sum()
    top = max(1, int(np.ceil(len(positive) * .1)))
    return dict(users=len(values), active_users=len(positive), events=int(total),
                counts_quantiles=quantiles(positive),
                top10_share=float(np.sort(positive)[-top:].sum() / total) if total else None)


def price_stats(frame: pd.DataFrame) -> dict:
    """Transaction-weighted prices, normalized over exactly the mapped categories."""
    frame = frame.dropna(subset=['category', 'price'])
    if frame.empty or not np.isfinite(frame.price).all() or (frame.price < 0).any() or frame.price.mean() <= 0:
        raise ValueError('invalid transaction prices')
    mean = float(frame.price.mean())
    groups = frame.groupby('category', observed=True)
    return dict(rows=len(frame), mean_price=mean,
                shares=(groups.size() / len(frame)).to_dict(),
                relative_means=(groups.price.mean() / mean).to_dict(),
                relative_quantiles={str(k): quantiles(v.price / mean) for k, v in groups})


def purchase_stats(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, users: Iterable[str] | None = None) -> dict:
    f = frame[(frame.timestamp >= start) & (frame.timestamp < end)].copy()
    f['day'] = f.timestamp.dt.floor('D')
    # H&M has date resolution and quantity-like duplicate rows: use the same unit on both sides.
    f = f.drop_duplicates(['user_id', 'product_id', 'day']).sort_values(['user_id', 'day', 'product_id'])
    counts = f.groupby('user_id').size()
    roster = counts if users is None else counts.reindex(users, fill_value=0)
    first = f.groupby(['user_id', 'product_id']).day.transform('min')
    f['repeat'] = f.day > first
    f['bin'] = pd.cut(f.user_id.map(counts), [0, 1, 4, 9, np.inf], labels=['1', '2-4', '5-9', '10+'])
    repeats = {str(k): dict(rows=len(g), rate=float(g.repeat.mean())) for k, g in f.groupby('bin', observed=True)}
    item_gap = f.groupby(['user_id', 'product_id']).day.diff().dt.total_seconds() / 86400
    visit = f[['user_id', 'day']].drop_duplicates().groupby('user_id').day.diff().dt.total_seconds() / 86400
    mapped = f.dropna(subset=['category'])
    cat = pd.crosstab(mapped.user_id, mapped.category)
    enough = cat.sum(axis=1) >= 5
    concentration = cat.max(axis=1) / cat.sum(axis=1)
    mid = start + (end - start) / 2
    halves = []
    for mask in [mapped.timestamp < mid, mapped.timestamp >= mid]:
        table = pd.crosstab(mapped.loc[mask, 'user_id'], mapped.loc[mask, 'category'])
        halves.append(table)
    eligible = halves[0].index[halves[0].sum(axis=1) >= 2].intersection(halves[1].index[halves[1].sum(axis=1) >= 2])
    columns = halves[0].columns.union(halves[1].columns)
    normalized = [t.reindex(index=eligible, columns=columns, fill_value=0) for t in halves]
    normalized = [t.div(t.sum(axis=1), axis=0) for t in normalized]
    shift = (normalized[0] - normalized[1]).abs().sum(axis=1) / 2
    return dict(start=str(start), end=str(end), unit='unique user-product-day purchases; repeats strictly on later days',
                activity=activity_stats(roster), repeat_rate=float(f.repeat.mean()) if len(f) else None,
                repeat_by_activity=repeats, repurchase_gap_days=quantiles(item_gap.dropna()),
                purchase_day_gap=quantiles(visit.dropna()),
                category_concentration=float(concentration[enough].mean()) if enough.any() else None,
                category_concentration_users=int(enough.sum()),
                half_window_category_tv=float(shift.mean()) if len(shift) else None,
                half_window_users=len(shift), mapped_purchase_rows=len(mapped))


def session_stats(events: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, seconds: int = 1800) -> dict:
    f = events[(events.timestamp >= start) & (events.timestamp < end)].copy()
    f = f.sort_values(['user_id', 'timestamp', 'row_id'], kind='stable')
    gap = f.groupby('user_id').timestamp.diff().dt.total_seconds()
    session = ((gap > seconds) | gap.isna()).groupby(f.user_id).cumsum()
    f['session'] = session
    grouped = f.groupby(['user_id', 'session'])
    summaries = grouped.agg(start=('timestamp', 'min'), end=('timestamp', 'max'), length=('event', 'size'),
                            purchase=('event', lambda x: bool((x == 'purchase').any())))
    margin = pd.Timedelta(seconds=seconds)
    complete = summaries[(summaries.start >= start + margin) & (summaries.end + margin < end)]
    tied = f.duplicated(['user_id', 'timestamp'], keep=False)
    prior_tied = tied.groupby(f.user_id).shift(1, fill_value=False)
    linked = gap.gt(0) & gap.le(seconds) & ~tied & ~prior_tied
    return dict(start=str(start), end=str(end), events=len(f), activity=activity_stats(f.groupby('user_id').size()),
                sessions=len(summaries), complete_sessions=len(complete),
                censored_sessions=len(summaries) - len(complete), tied_event_rows=int(tied.sum()),
                length_quantiles=quantiles(complete.length),
                duration_seconds=quantiles((complete.end - complete.start).dt.total_seconds()),
                purchase_rate=float(complete.purchase.mean()) if len(complete) else None,
                within_gap_seconds=quantiles(gap[linked]))


def distance(actual: dict, target: dict) -> dict:
    categories = sorted(target['price']['relative_means'])
    price = actual['price']; truth = target['price']
    if set(categories) - set(price['relative_means']):
        raise ValueError('missing category in generated purchases')
    a, b = actual['session'], target['session']
    values = dict(
        price_mae=float(np.mean([abs(price['relative_means'][k] - truth['relative_means'][k]) for k in categories])),
        price_quantile_mae=float(np.mean([np.abs(np.array(price['relative_quantiles'][k]) - truth['relative_quantiles'][k]).mean() for k in categories])),
        category_tv=sum(abs(price['shares'].get(k, 0) - truth['shares'][k]) for k in categories) / 2,
        activity_top10_error=abs(a['activity']['top10_share'] - b['activity']['top10_share']),
        session_purchase_error=abs(a['purchase_rate'] - b['purchase_rate']))
    for key, output in [('length_quantiles', 'session_length_error'), ('within_gap_seconds', 'gap_error')]:
        values[output] = float(np.mean(np.abs(np.array(a[key]) - b[key]) / np.maximum(b[key], 1)))
    values['behavior_objective'] = float(np.mean([values[k] for k in ['activity_top10_error', 'session_purchase_error', 'session_length_error', 'gap_error']]))
    return values
