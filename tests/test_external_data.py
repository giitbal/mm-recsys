from __future__ import annotations

import copy
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

from src.common.config import load_config
from src.external_data.calibration import calibrated_config
from src.external_data.deepfashion import annotation_rows
from src.external_data.hm_prepare import day_boundaries, prepare
from src.external_data.io import extract_member, inventory, load_spec
from src.external_data.retailrocket import probabilities, transition_counts


def test_markov_does_not_cross_users_sessions_ties_or_censor_boundary():
    origin = pd.Timestamp('2020-01-01', tz='UTC')
    frame = pd.DataFrame([
        ('a', 0, 'view'), ('a', 60, 'cart'), ('a', 120, 'purchase'),
        ('a', 4000, 'view'), ('b', 60, 'purchase'),
        ('c', 0, 'view'), ('c', 60, 'cart'), ('c', 60, 'purchase'), ('c', 120, 'view'),
        ('d', 4900, 'view')], columns=['visitorid', 'seconds', 'event'])
    frame['timestamp'] = origin + pd.to_timedelta(frame.seconds, unit='s')
    frame['row_id'] = np.arange(len(frame))
    counts, audit = transition_counts(frame, origin + pd.Timedelta(seconds=5000), 1800)
    assert counts['view']['cart'] == 1
    assert counts['cart']['purchase'] == 1
    assert counts['purchase']['view'] == 0
    assert counts['purchase']['exit'] == 2
    assert counts['view']['exit'] == 1  # c's final view; a/d have incomplete windows
    assert audit['ambiguous_tied_event_rows'] == 2
    assert counts == transition_counts(frame.sample(frac=1, random_state=3), origin + pd.Timedelta(seconds=5000), 1800)[0]
    assert all(sum(row.values()) == pytest.approx(1) for row in probabilities(counts, 1).values())


def test_chronological_days_stay_together_and_reject_empty_partitions():
    a, b = day_boundaries({f'2020-01-{i:02d}': 10 for i in range(1, 11)})
    assert (a, b) == ('2020-01-08', '2020-01-09')
    with pytest.raises(ValueError): day_boundaries({'2020-01-01': 100})


def test_archive_copy_rejects_modified_cache_and_changed_member(tmp_path):
    z = tmp_path / 'source.zip'; out = tmp_path / 'raw/file.csv'
    with ZipFile(z, 'w') as archive: archive.writestr('file.csv', 'a,b\n1,2\n')
    one = extract_member(z, 'file.csv', out)
    assert one == extract_member(z, 'file.csv', out)
    out.write_text('a,b\n3,4\n')
    with pytest.raises(ValueError, match='changed'): extract_member(z, 'file.csv', out)


def test_annotation_parser_rejects_incomplete_data():
    assert annotation_rows('2\nname label\na.jpg 1\nb.jpg 2\n') == [['a.jpg', '1'], ['b.jpg', '2']]
    with pytest.raises(ValueError): annotation_rows('3\nname label\na.jpg 1\n')


def test_calibration_reuses_existing_keys_and_preserves_original_recipe():
    base = load_config(); before = copy.deepcopy(base)
    names = list(base['simulator']['taxonomy'])
    hm = {'category_purchase_shares': dict(zip(names, [.6, .1, .1, .1, .1])),
          'relative_category_price': {k: 1.2 for k in names}}
    matrix = {k: {'view': .3, 'cart': .2, 'purchase': .1, 'exit': .4} for k in ('view', 'cart', 'purchase')}
    fitted = calibrated_config(base, hm, {'fitted_transitions': matrix}, .5)
    assert base == before
    assert fitted['simulator']['transitions']['cart'] == matrix['cart']
    assert fitted['simulator']['transitions']['search'] == base['simulator']['transitions']['search']
    preferences = [p['category_preferences'] for p in fitted['simulator']['personas'].values()]
    assert all(sum(row) == pytest.approx(1) for row in preferences)
    assert len({tuple(row) for row in preferences}) > 1


def hm_fixture(tmp_path: Path) -> dict:
    spec = load_spec('config/external_data.yaml')
    spec.update(source_dir=str(tmp_path / 'source'), work_dir=str(tmp_path / 'work'), results_dir=str(tmp_path / 'results'))
    spec['hm'].update(user_limit=2, chunk_rows=7)
    Path(spec['source_dir']).mkdir()
    articles = pd.DataFrame(dict(article_id=['0000000001', '0000000002'], product_code=['0000001', '0000002'],
        prod_name=['Shirt', 'Shoe'], product_group_name=['Garment Upper body', 'Shoes'],
        garment_group_name=['Shirt', 'Shoe'], product_type_name=['Shirt', 'Shoe'],
        colour_group_name=['Black', 'White'], graphical_appearance_name=['Solid', 'Solid'], detail_desc=['shirt', None]))
    transactions = pd.DataFrame([dict(t_dat=f'2020-01-{day:02d}', customer_id=uid, article_id=f'{pid:010d}',
                                     price=.1 if day <= 8 else 10000, sales_channel_id=1)
                                 for day in range(1, 11) for uid in ('a', 'b') for pid in (1, 2)])
    with ZipFile(Path(spec['source_dir']) / spec['hm']['archive'], 'w') as z:
        for name, frame in {'articles.csv': articles, 'customers.csv': pd.DataFrame({'customer_id': ['a', 'b']}),
                            'transactions_train.csv': transactions, 'sample_submission.csv': pd.DataFrame({'customer_id': ['a'], 'prediction': ['']})}.items():
            z.writestr(name, frame.to_csv(index=False))
    return spec


def test_hm_uses_train_prices_preserves_ids_and_does_not_invent_exposures(tmp_path):
    spec = hm_fixture(tmp_path)
    report = prepare(spec)
    root = Path(spec['work_dir']) / 'hm'
    products = pd.read_parquet(root / 'products.parquet')
    train = pd.read_parquet(root / 'split/train.parquet')
    valid = pd.read_parquet(root / 'split/valid.parquet')
    assert set(products.product_id) == {'HM-0000000001', 'HM-0000000002'}
    assert products.price.tolist() == pytest.approx([.1, .1])
    assert train.impression_id.isna().all()
    assert not (root / 'impressions.parquet').exists()
    assert train.timestamp.max() < valid.timestamp.min()
    assert report['calibration']['train_transactions'] == 32
    manifest = json.loads((root / 'split_manifest.json').read_text())
    assert train.timestamp.max() < pd.Timestamp(manifest['boundaries']['train']['end']) < valid.timestamp.min()


def test_inventory_refuses_reusing_changed_source_version(tmp_path):
    spec = hm_fixture(tmp_path)
    one = inventory(spec)
    assert inventory(spec)['identity'] == one['identity']
    changed = copy.deepcopy(spec); changed['seed'] += 1
    with pytest.raises(ValueError, match='new work_dir'): inventory(changed)
