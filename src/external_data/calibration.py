"""Executable versioned simulator recipe derived from real train data."""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import yaml

from src.common.artifacts import fingerprint, write_json
from src.common.config import load_config
from src.external_data.io import paths
from src.external_data.retailrocket import transition_counts, probabilities
from src.simulator.generate import generate


def calibrated_config(base: dict, hm: dict, retail: dict, blend: float) -> dict:
    cfg = copy.deepcopy(base)
    sim = cfg['simulator']
    shares = hm['category_purchase_shares']
    names = list(sim['taxonomy'])
    if set(names) != set(shares): raise ValueError('calibration must cover every simulator L1 category')
    target = np.array([shares[n] for n in names])
    for persona in sim['personas'].values():
        mixed = (1 - blend) * np.array(persona['category_preferences']) + blend * target
        persona['category_preferences'] = (mixed / mixed.sum()).tolist()
    # Preserve the simulator's monetary unit; H&M prices only adjust relative ranges.
    for name, limits in sim['category_price_ranges'].items():
        ratio = hm['relative_category_price'][name]
        sim['category_price_ranges'][name] = [max(1000, int(v * ratio)) for v in limits]
    sim['transitions'].update(retail['fitted_transitions'])
    sim['cart_reference_cvr'] = sum(p['ratio'] * p['cvr'] for p in sim['personas'].values())
    return cfg


def run(spec: dict) -> dict:
    _, work, results = paths(spec)
    hm = json.loads((results / 'hm_data.json').read_text())['calibration']
    retail = json.loads((results / 'retailrocket.json').read_text())
    cfg = calibrated_config(load_config(), hm, retail, spec['calibration']['preference_blend'])
    cfg['paths'].update(data_dir=str(work / 'simulator-dev'), model_dir=str(work / 'models/simulator-dev'),
                        split_dir=str(work / 'simulator-dev/split'), results_dir=str(results / 'simulator'))
    cfg['paths']['by_scale'] = {'full': dict(data_dir=str(work / 'simulator-full'),
        split_dir=str(work / 'simulator-full/split'), model_dir=str(work / 'models/simulator-full'))}
    cfg['external_calibration'] = dict(hm=fingerprint(hm), retailrocket=fingerprint(retail['fitted_transitions']),
                                     source_config=fingerprint(spec), primary_acceptance='UNMEASURED')
    config_path = work / 'calibrated_simulator.yaml'
    config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    # A separate pilot exercises the actual generator without replacing dev/full artifacts.
    pilot = copy.deepcopy(cfg)
    pilot['paths']['data_dir'] = str(work / 'simulator-pilot')
    for key, config_key in [('n_products', 'pilot_products'), ('n_users', 'pilot_users'), ('n_events', 'pilot_events')]:
        pilot['simulator'][key] = spec['calibration'][config_key]
    manifest = generate(pilot)
    events = pd.read_parquet(work / 'simulator-pilot/events.parquet')
    observed = events[events.event_type.isin(['view', 'cart', 'purchase'])].rename(columns={'user_id': 'visitorid', 'event_type': 'event'}).copy()
    observed['row_id'] = np.arange(len(observed))
    counts, diagnostics = transition_counts(observed, events.timestamp.max(), spec['retailrocket']['session_seconds'])
    rates = probabilities(counts, 0)
    distance = {state: sum(abs(rates[state][dest] - retail['fitted_transitions'][state][dest])
                            for dest in rates[state]) / 2 for state in rates}
    report = dict(status='PASS', acceptance='UNMEASURED', config_path=str(config_path), config_fingerprint=fingerprint(cfg),
        hm_parameters={'persona_category_preferences': {k: v['category_preferences'] for k, v in cfg['simulator']['personas'].items()},
                       'category_price_ranges': cfg['simulator']['category_price_ranges']},
        retailrocket_parameters=cfg['simulator']['transitions'], pilot_manifest=manifest,
        generated_observed_transitions=rates, generated_total_variation_from_real_train=distance, pilot_diagnostics=diagnostics,
        limitations=['H&M mapped categories only; unsupported categories excluded from calibration but retained in recommendation',
                    'persona memberships, search/exit restart, exposure counts remain synthetic',
                    'persona conversion adjustments mean generated aggregate transitions need not equal fitted matrix',
                    'pilot validates recipe execution, not full-scale quality, CTR/CVR or final acceptance'])
    write_json(results / 'calibration.json', report)
    return report
