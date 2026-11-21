from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.common.artifacts import file_hash
from src.common.config import load_config
from src.serving.main import create_app
from src.serving.memory_store import MemoryFeatureStore


@pytest.fixture
def shop(tmp_path):
    cfg = load_config()
    cfg['paths'].update(data_dir=str(tmp_path / 'data'), model_dir=str(tmp_path / 'models'), results_dir=str(tmp_path / 'results'))
    cfg['serving']['plugins'] = dict(search='no_search_plugin', recommend='no_recommend_plugin')
    cfg['serving']['ct']['enabled'] = False
    root = Path(cfg['paths']['data_dir']); root.mkdir()
    rows = [dict(product_id=f'P{i:06}', name=f'black bag {i}', category_l1=category,
                 category_l2='bags', category_l3='bags', brand='Simulator', color='black', style='casual',
                 price=price, image_path=f'P{i:06}.jpg', created_at='2026-01-01', description_en='black bag')
            for i, category, price in [(1, 'fashion', 1234.5), (2, 'fashion', 9000.), (3, 'sports', 2000.)]]
    for row in rows:
        Image.new('RGB', (16, 16), 'black').save(root / row['image_path'])
    pd.DataFrame(rows).to_parquet(root / 'products.parquet')
    manifest = dict(generation_fingerprint=str(tmp_path), file_hashes={'products.parquet': file_hash(root / 'products.parquet')})
    (root / 'split_manifest.json').write_text(json.dumps(manifest))
    with TestClient(create_app(cfg, feature_store=MemoryFeatureStore(50, 1800, 86400))) as client:
        yield client, cfg, root


def test_catalog_pagination_filters_order_and_original_prices(shop):
    client, _, _ = shop
    result = client.get('/api/storefront/products', params=dict(category='fashion', sort='price-desc', limit=1)).json()
    assert result['pagination']['total'] == 2 and result['pagination']['hasNext']
    assert result['items'][0]['id'] == 'P000002'
    detail = client.get('/api/storefront/products/P000001').json()
    assert detail['variants'][0]['price'] == 1234.5  # Preserve simulator price in KRW, not USD cents.
    assert detail['images'][0]['url'].endswith('/images/P000001')
    ordered = client.get('/api/storefront/products', params={'ids': 'P000003,P000001,P000003,unknown'}).json()
    assert [item['id'] for item in ordered['items']] == ['P000003', 'P000001']
    assert len(client.get('/api/storefront/categories').json()) == 2
    assert client.get('/api/storefront/products?limit=101').status_code == 422
    assert client.get('/api/storefront/products?sort=unsafe').status_code == 422
    assert client.get('/api/storefront/products/unknown').status_code == 404


def test_images_only_resolve_catalog_ids_and_stay_inside_root(shop):
    client, _, root = shop
    response = client.get('/api/storefront/images/P000001')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
    assert client.get('/api/storefront/images/unknown').status_code == 404
    target = root / 'P000002.jpg'
    target.unlink(); target.symlink_to(root.parent / 'private.txt')
    (root.parent / 'private.txt').write_text('do not expose')
    assert client.get('/api/storefront/images/P000002').status_code == 404


def test_absent_or_mismatched_evidence_is_never_reported_as_measured(shop):
    client, cfg, _ = shop
    result = client.get('/api/storefront/operations').json()
    assert result['ab']['status'] == 'UNMEASURED' and result['ct']['enabled'] is False
    results = Path(cfg['paths']['results_dir']); results.mkdir()
    (results / 'deployment.json').write_text(json.dumps(dict(data_fingerprint='other-data')))
    result = client.get('/api/storefront/operations').json()
    assert result['ab']['status'] == 'UNMEASURED'
    assert 'identity' in result['ab']['reason']


def test_missing_catalog_returns_unavailable_not_dummy_products(shop):
    client, _, root = shop
    (root / 'split_manifest.json').unlink()
    assert client.get('/api/storefront/products').status_code == 503
