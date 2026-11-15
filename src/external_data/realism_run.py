"""Versioned price/behavior ablations, valid selection and frozen seed evaluation."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import yaml

from src.common.artifacts import file_hash, fingerprint, write_json
from src.external_data.calibration import correct_price_ranges
from src.external_data.realism_data import plan, prepare
from src.external_data.realism_metrics import price_stats, purchase_stats, session_stats, distance
from src.external_data.retailrocket import transition_counts, probabilities
from src.simulator.catalog import make_catalog
from src.simulator.users import make_users
from src.simulator.events import make_events
from src.simulator.generate import generate


def sources() -> dict:
    return {str(p): file_hash(p) for p in sorted(Path('src').rglob('*.py'))}


def base_config(spec: dict) -> dict:
    # Reproduce the previous combined recipe exactly before applying new corrections.
    cfg = yaml.safe_load((Path(spec['source_expansion']) / 'simulator/42-both/config.yaml').read_text())
    cfg['seed'] = spec['seed']
    cfg['simulator'].update(n_products=spec['products'], n_users=spec['users'], n_events=spec['events'],
                            window_days=spec['purchase_window_days'])
    cfg['recommend']['candidate'].update(epochs=spec['candidate_epochs'], threads=spec['threads'])
    cfg['recommend']['ranking'].update(epochs=spec['ranking_epochs'], threads=spec['threads'])
    return cfg


def simulate(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg['seed'])
    products = make_catalog(cfg, rng)
    users = make_users(cfg, rng)
    events, _ = make_events(cfg, products, users, rng)
    return products, users, events


def measure(cfg: dict, products: pd.DataFrame, users: pd.DataFrame, events: pd.DataFrame) -> dict:
    spec, _, _ = plan()
    end = pd.Timestamp(cfg['simulator']['reference_time'])
    start = end - pd.Timedelta(days=spec['purchase_window_days'])
    if events.timestamp.min() < start or events.timestamp.max() >= end:
        raise ValueError('generated events escaped configured observation window')
    purchases = events[events.event_type == 'purchase'].merge(
        products[['product_id', 'category_l1', 'price']], on='product_id', how='left').rename(columns={'category_l1': 'category'})
    observable = events[events.event_type.isin(['view', 'cart', 'purchase'])].rename(columns={'event_type': 'event'}).copy()
    observable['row_id'] = np.arange(len(observable))
    begin = end - pd.Timedelta(days=spec['session_window_days'])
    counts, audit = transition_counts(observable[observable.timestamp >= begin].rename(columns={'user_id': 'visitorid'}), end, spec['session_seconds'])
    return dict(price=price_stats(purchases), purchase=purchase_stats(purchases, start, end, users.user_id),
                session=session_stats(observable, begin, end, spec['session_seconds']),
                transitions={s:({d:n/sum(row.values()) for d,n in row.items()} if sum(row.values()) else None)
                             for s,row in counts.items()}, transition_diagnostics=audit,
                events=len(events), products=len(products), users=len(users))


def pilot(name: str, cfg: dict, targets: dict, work: Path, output: Path) -> dict:
    root = work / 'pilots'; root.mkdir(exist_ok=True)
    report = output / 'pilots'; report.mkdir(exist_ok=True)
    started = time.perf_counter()
    actual = measure(cfg, *simulate(cfg))
    record = dict(name=name, seed=cfg['seed'], config_fingerprint=fingerprint(cfg), actual=actual,
                  distances={split: distance(actual, targets[split]) for split in ['train', 'valid']},
                  seconds=time.perf_counter() - started)
    (root / f'{name}.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))
    write_json(report / f'{name}.json', record)
    print(name, record['distances']['valid'], flush=True)
    return record


def tune_prices(name: str, cfg: dict, targets: dict, spec: dict, work: Path, output: Path) -> tuple[dict, list]:
    trials = []
    configs = []
    current = copy.deepcopy(cfg)
    for step in range(spec['price_iterations'] + 1):
        record = pilot(f'{name}-{step}', current, targets, work, output)
        configs.append(copy.deepcopy(current)); trials.append(record)
        if step < spec['price_iterations']:
            current = correct_price_ranges(current, targets['train']['price']['relative_means'],
                                            record['actual']['price']['relative_means'], spec['price_damping'])
    chosen = min(range(len(trials)), key=lambda i: trials[i]['distances']['valid']['price_mae'])
    return configs[chosen], trials


def tune() -> None:
    spec, work, output = plan(); prepare()
    if (output / 'selection.json').exists():
        check_selection(); return
    targets = json.loads((output / 'targets.json').read_text())
    base = base_config(spec)
    baseline = pilot('baseline', base, targets, work, output)
    price, price_trials = tune_prices('price', base, targets, spec, work, output)
    profile = json.loads((work / 'behavior_profile.json').read_text())
    choices = [(base, baseline)]
    for trial in spec['behavior_trials']:
        cfg = copy.deepcopy(base)
        cfg['simulator']['realism'] = dict(profile, **trial, version='realism-v4')
        record = pilot(trial['name'], cfg, targets, work, output)
        choices.append((cfg, record))
    behavior, best = min(choices, key=lambda pair: pair[1]['distances']['valid']['behavior_objective'])
    combined, combined_trials = tune_prices('combined', behavior, targets, spec, work, output)
    recipes = dict(baseline=base, price=price, behavior=behavior, combined=combined)
    (work / 'recipes').mkdir(exist_ok=True)
    for name, cfg in recipes.items():
        (work / 'recipes' / f'{name}.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))
    write_json(output / 'selection.json', dict(status='FROZEN', acceptance='UNMEASURED',
        behavior_selected=best['name'], price_selected=min(price_trials,key=lambda x:x['distances']['valid']['price_mae'])['name'],
        combined_selected=min(combined_trials,key=lambda x:x['distances']['valid']['price_mae'])['name'],
        source_hashes=sources(), config_sha256=file_hash(Path('config/external_realism.yaml')),
        target_sha256=file_hash(output / 'targets.json'),
        recipe_hashes={str(p):file_hash(p) for p in (work / 'recipes').glob('*.yaml')},
        fitting='price updates use train target only; iterations/behavior choice selected on real valid; no recommendation metric selection',
        test_scope='Real test was previously inspected in v1-v3: exploratory transfer, not independent holdout'))
    print('Selection frozen:', best['name'], flush=True)


def check_selection() -> dict:
    _, _, output = plan()
    selection = json.loads((output / 'selection.json').read_text())
    if selection['source_hashes'] != sources(): raise ValueError('source changed after freeze')
    if file_hash(Path('config/external_realism.yaml')) != selection['config_sha256']: raise ValueError('plan changed after freeze')
    if file_hash(output / 'targets.json') != selection['target_sha256']: raise ValueError('targets changed after freeze')
    if not all(file_hash(Path(p)) == h for p,h in selection['recipe_hashes'].items()): raise ValueError('recipe changed after freeze')
    return selection


def evaluate() -> None:
    spec, work, output = plan(); check_selection()
    targets = json.loads((output / 'targets.json').read_text())
    records = []
    for seed in spec['evaluation_seeds']:
        for name in ['baseline', 'price', 'behavior', 'combined']:
            path = output / 'runs' / f'{seed}-{name}.json'
            if path.exists():
                records.append(json.loads(path.read_text())); continue
            cfg = yaml.safe_load((work / 'recipes' / f'{name}.yaml').read_text())
            cfg['seed'] = seed
            root = work / 'runs' / f'{seed}-{name}'; root.mkdir(parents=True,exist_ok=True)
            cfg['paths'].update(data_dir=str(root / 'data'), split_dir=str(root / 'data/split'), model_dir=str(root / 'models'),
                                results_dir=str(output / 'models' / f'{seed}-{name}'))
            (root / 'config.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))
            started = time.perf_counter()
            manifest = generate(cfg)
            actual = measure(cfg, *(pd.read_parquet(root / 'data' / f'{kind}.parquet') for kind in ['products', 'users', 'events']))
            record = dict(name=name, seed=seed, data_fingerprint=manifest['generation_fingerprint'],
                          config_sha256=file_hash(root / 'config.yaml'), actual=actual,
                          distances={s:distance(actual,targets[s]) for s in ['train','valid','test']},
                          seconds=time.perf_counter()-started)
            write_json(path,record); records.append(record)
            print('Evaluated',seed,name,record['distances']['test'],flush=True)
    aggregates = {}
    for name in ['baseline', 'price', 'behavior', 'combined']:
        rows = [r for r in records if r['name']==name]
        aggregates[name] = {split:{key:dict(mean=float(np.mean([r['distances'][split][key] for r in rows])),
                                          std=float(np.std([r['distances'][split][key] for r in rows],ddof=1)))
                                  for key in rows[0]['distances'][split]} for split in ['train','valid','test']}
    write_json(output / 'comparison.json',dict(status='PASS',acceptance='UNMEASURED',runs=len(records),aggregate=aggregates))
    # Catalog sensitivity is diagnostic only and never used to tune the frozen recipes.
    for size in [spec['products'], 105542]:
        cfg = yaml.safe_load((work / 'recipes/baseline.yaml').read_text()); cfg['seed']=spec['evaluation_seeds'][0]
        cfg['simulator']['n_products']=size
        actual=measure(cfg,*simulate(cfg))
        write_json(output / f'catalog_control_{size}.json',dict(products=size,actual=actual,
            scope='Fixed users/events/window; different catalog changes sampled trajectories. Descriptive size sensitivity, no test-based correction.'))
    # More events expose purchase cohorts that are too sparse in the 100k-event pilot.
    for name in ['baseline', 'combined']:
        cfg=yaml.safe_load((work/'recipes'/f'{name}.yaml').read_text());cfg['seed']=spec['evaluation_seeds'][0]
        cfg['simulator']['n_events']=500000
        actual=measure(cfg,*simulate(cfg))
        write_json(output/f'density_control_{name}.json',dict(name=name,events=500000,actual=actual,
            scope='Additional diagnostic at fixed 28-day window / 1000 users / 3000 products; cannot pool with 100k-event quality scores; no parameter reselection.'))


def train_models() -> None:
    from src.recommendation.train_two_tower import train as candidate_train, load_bundle
    from src.recommendation.train_deepfm import train as ranking_train
    from src.recommendation.eval_ranking import evaluate as ranking_evaluate
    from src.recommendation.datasets import read_data
    from src.recommendation.eval_candidate import Evaluation
    spec, work, output = plan(); check_selection()
    for seed in spec['evaluation_seeds']:
        for name in ['baseline','combined']:
            cfg = yaml.safe_load((work / 'runs' / f'{seed}-{name}' / 'config.yaml').read_text())
            out=Path(cfg['paths']['results_dir']); out.mkdir(parents=True,exist_ok=True)
            if (out/'result.json').exists(): continue
            models=Path(cfg['paths']['model_dir'])
            if not (models/'v1.0/meta.json').exists(): candidate_train(cfg,out/'candidate_training.json',models/'v1.0')
            if not (out/'ranking_selection_dev.json').exists(): ranking_train(cfg)
            ranking_evaluate(cfg,'valid',output=out/'ranking_valid.json')
            write_json(out/'frozen.json',dict(source_hashes=sources(),model_hashes={str(p):file_hash(p) for p in models.rglob('*.pt')}))
            data=read_data(cfg['paths']['data_dir'],'test')
            model,encoder,table,_=load_bundle(models/'v1.0',data,cfg)
            recall=Evaluation(data,encoder,table,cfg,'test').model(model)
            ranked=ranking_evaluate(cfg,'test',output=out/'ranking_test.json')
            write_json(out/'result.json',dict(name=name,seed=seed,candidate=recall,ranking=ranked['metrics'],classification=ranked['classification'],
                scope='Fresh train/valid-selected models on each generated dataset. Synthetic truths differ: score change is not real-world uplift.',acceptance='UNMEASURED'))
            print('Model evaluation complete',seed,name,flush=True)


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--task',choices=['prepare','tune','evaluate','train','all'],default='all')
    task=parser.parse_args().task
    for name, fn in [('prepare',prepare),('tune',tune),('evaluate',evaluate),('train',train_models)]:
        if task in [name,'all']: fn()


if __name__=='__main__': main()
