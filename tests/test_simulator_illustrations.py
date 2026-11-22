import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from src.common.config import load_config
from src.simulator.catalog import leaves, render_product
from src.simulator.generate import generate

CONFIG = 'config.yaml'


def test_artwork_varies_shape_and_construction_with_color_and_style_fixed():
    cfg = load_config(CONFIG)
    row = dict(category_l1='accessories', category_l2='bags', category_l3='tote bag',
               color='black', style='regular')
    images = [np.asarray(render_product(row, cfg, i)) for i in range(24)]
    assert all(image.shape == (224, 224, 3) for image in images)
    assert len({im.tobytes() for im in images}) == 24
    # Ignore fabric / stitching colors: the first six cuts must have distinct outlines.
    outlines = [np.any(im != im[0, 0], axis=2) for im in images[:6]]
    for i, mask in enumerate(outlines):
        for other in outlines[:i]:
            assert np.count_nonzero(mask ^ other) > 700
    assert render_product(dict(row, product_id='P999999', brand='Other'), cfg, 2).tobytes() == images[2].tobytes()

    for kind, mid, leaf in leaves(cfg):
        subtype = dict(row, category_l1=kind, category_l2=mid, category_l3=leaf)
        variants = {render_product(subtype, cfg, i).tobytes() for i in range(6)}
        assert len(variants) >= 3, leaf


def test_artwork_dataset_lineage_and_reproducibility(tmp_path):
    cfg = load_config(CONFIG)
    cfg['simulator'].update(n_products=450, n_users=120, n_events=4000)
    folder = tmp_path / 'designs'
    manifest = generate(cfg, folder)
    assert manifest['file_hashes'] == generate(cfg, tmp_path / 'replica')['file_hashes']
    rows = pd.read_parquet(folder / 'products.parquet')
    images = json.loads((folder / 'image_manifest.json').read_text())
    for row in rows.itertuples():
        assert hashlib.sha256((folder / row.image_path).read_bytes()).hexdigest() == images[row.image_path]
        assert images[row.image_path] == row.visual_group == row.image_sha256
    cfg['simulator'].pop('image_recipe')
    with pytest.raises(ValueError, match='image_recipe'):
        generate(cfg, folder)
    cfg['simulator']['image_recipe'] = 'typo'
    with pytest.raises(ValueError, match='image_recipe'):
        render_product(rows.iloc[0].to_dict(), cfg)


def test_default_full_recipe_matches_packaged_measurement_and_isolated_shop(monkeypatch):
    from pathlib import Path
    from src.common.artifacts import fingerprint
    from src.simulator.generate import generation_identity

    monkeypatch.setenv('SCALE', 'full')
    default = load_config('config.yaml')
    measured = json.loads(Path('docs/submission/dashboard/evaluation_full_test.json').read_text())
    identity = fingerprint(generation_identity(default))
    assert default['simulator']['image_variants'] == 24
    assert default['paths']['data_dir'] == 'data/full-illustrations-v1'
    assert measured['data_fingerprint'] == identity
    for path in ('config/catalog_illustrations_v1.yaml', 'docs/submission/integration_config.yaml'):
        assert fingerprint(generation_identity(load_config(path))) == identity
    assert load_config('config/full_realism_v4.yaml')['simulator']['image_recipe'] == 'illustrations-v1'
    default['simulator']['image_recipe'] = 'silhouettes'
    with pytest.raises(ValueError, match='image_recipe'):
        generation_identity(default)
