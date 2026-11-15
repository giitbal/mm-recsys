"""Validated, opt-in aggregate behavior parameters consumed by the simulator."""
from __future__ import annotations

import numpy as np


def validate(profile: dict) -> None:
    if profile.get('version') != 'realism-v4':
        raise ValueError('unsupported realism profile')
    for name in ['activity_quantiles', 'within_gap_quantiles']:
        array = np.asarray(profile[name], dtype=float)
        if array.ndim != 1 or len(array) < 2 or not np.isfinite(array).all() or (array <= 0).any() or (np.diff(array) < 0).any():
            raise ValueError(f'invalid {name}')
    if profile['within_gap_quantiles'][-1] > profile['session_seconds']:
        raise ValueError('within-session interval exceeds session threshold')
    matrix = np.asarray(profile['transitions'], dtype=float)
    thresholds = np.asarray(profile['activity_thresholds'])
    if (thresholds.ndim != 1 or (thresholds <= 0).any() or (np.diff(thresholds) <= 0).any()
            or matrix.shape != (len(thresholds) + 1, 3, 4) or not np.isfinite(matrix).all()
            or (matrix < 0).any() or not np.allclose(matrix.sum(axis=2), 1)):
        raise ValueError('invalid conditional Markov profile')


def conditional_rows(profile: dict, previous: np.ndarray, state: str) -> np.ndarray:
    groups = np.digitize(previous, profile['activity_thresholds'])
    return np.asarray(profile['transitions'])[groups, ['view', 'cart', 'purchase'].index(state)]
