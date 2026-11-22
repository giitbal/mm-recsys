"""Read-only storefront views of the same simulator catalog and execution evidence."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from dashboard.assets import ab_result, catalog, image_path
from dashboard.data import ct_log
from src.search.text import display_text


def create_router(cfg: dict) -> APIRouter:
    router = APIRouter(prefix='/api/storefront', tags=['storefront'])
    root = Path(cfg['paths']['data_dir'])
    results = Path(cfg['paths']['results_dir'])

    def source() -> tuple[pd.DataFrame, str]:
        try:
            manifest = json.loads((root / 'split_manifest.json').read_text())
            identity = manifest['generation_fingerprint']
            return catalog(str(root), identity), identity
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(503, '상품 카탈로그 준비 또는 fingerprint 확인 실패') from error

    def product(row: pd.Series) -> dict:
        pid, name = str(row['product_id']), display_text(str(row['name']))
        image = dict(url=f'/api/live/api/storefront/images/{quote(pid, safe="")}', alt=name)
        return dict(id=pid, slug=pid, name=name, description=display_text(str(row.get('description_en', ''))),
            images=[image], status='active', brandId=str(row['brand']),
            categoryIds=[str(row['category_l1'])], tags=[display_text(str(row[k])) for k in ('category_l3', 'color', 'style')],
            variants=[dict(id=pid, productId=pid, sku=pid, name=display_text(str(row['color'])),
                price=float(row['price']), currency='KRW', options=[], images=[image],
                inventory=dict(quantity=0, trackInventory=False, allowBackorder=True))],
            rating=0, reviewCount=0, featured=False, createdAt=str(row['created_at']), updatedAt=str(row['created_at']))

    @router.get('/products')
    def products(page: int = Query(1, ge=1, le=100000), limit: int = Query(24, ge=1, le=100),
                 category: str | None = Query(None, max_length=200),
                 sort: Literal['newest', 'price-asc', 'price-desc', 'name'] = 'newest',
                 ids: str | None = Query(None, max_length=4000)) -> dict:
        rows, identity = source()
        if ids is not None:
            selected = list(dict.fromkeys(ids.split(',')))
            if len(selected) > 100:
                raise HTTPException(422, '최대 100개 상품을 조회할 수 있습니다.')
            rows = rows.loc[[pid for pid in selected if pid in rows.index]]
        else:
            if category is not None:
                rows = rows[rows.category_l1 == category]
            field = {'newest': 'created_at', 'price-asc': 'price', 'price-desc': 'price', 'name': 'name'}[sort]
            rows = rows.reset_index(drop=True).sort_values([field, 'product_id'], ascending=[sort not in ('newest', 'price-desc'), True])
        total = len(rows)
        return dict(items=[product(row) for _, row in rows.iloc[(page-1)*limit:page*limit].iterrows()],
            data_fingerprint=identity, pagination=dict(total=total, page=page, limit=limit,
                totalPages=math.ceil(total/limit), hasNext=page*limit < total, hasPrev=page > 1))

    @router.get('/categories')
    def categories() -> list[dict]:
        rows, _ = source()
        return [dict(id=str(name), slug=str(name), name=display_text(str(name)), description='', order=i,
                     image=product(group.iloc[0])['images'][0])
                for i, (name, group) in enumerate(rows.groupby('category_l1', sort=True))]

    @router.get('/products/{product_id}')
    def detail(product_id: str) -> dict:
        rows, _ = source()
        if product_id not in rows.index:
            raise HTTPException(404, '상품이 없습니다.')
        return product(rows.loc[product_id])

    @router.get('/images/{product_id}')
    def image(product_id: str) -> FileResponse:
        rows, _ = source()
        if product_id not in rows.index:
            raise HTTPException(404, '상품이 없습니다.')
        try:
            path = image_path(dict(data_dir=str(root)), rows.loc[product_id])
            if not path.is_file():
                raise FileNotFoundError(path)
            return FileResponse(path, headers={'Cache-Control': 'private, max-age=3600'})
        except (OSError, ValueError) as error:
            raise HTTPException(404, '상품 이미지를 읽을 수 없습니다.') from error

    @router.get('/operations')
    def operations(request: Request) -> dict:
        _, identity = source()
        ab: dict = dict(status='UNMEASURED', reason='현재 배포와 연결된 A/B 결과가 없습니다.')
        try:
            # Validate against the running API, as well as the report deployment file.
            active_path = results / 'deployment.json'
            if active_path.exists():
                active = json.loads(active_path.read_text())
                if (active['data_fingerprint'] != identity
                        or Path(active['data_dir']).resolve() != root.resolve()
                        or Path(active['model_dir']).resolve() != Path(cfg['paths']['model_dir']).resolve()):
                    raise ValueError('현재 API와 A/B 배포 identity가 다릅니다.')
                ab = ab_result(results) or ab
        except (OSError, ValueError, KeyError) as error:
            ab = dict(status='UNMEASURED', reason=str(error))
        components = request.app.state.ct
        ct: dict = dict(enabled=components is not None, serving_version=request.app.state.model_version)
        if components:
            spec, journal, registry = components
            state = registry.read()
            ct.update(active=state['active'], new_events=journal.count_since(state['last_success_seq'], journal.high_watermark()),
                threshold=spec['retrain_log_threshold'], logs=ct_log(registry.log.parent, limit=30),
                versions=[{k: record.get(k) for k in ('version', 'date', 'parent', 'status', 'metrics')}
                          for record in state['versions'].values()])
        return dict(data_fingerprint=identity, ab=ab, ct=ct,
            search_ready=request.app.state.search is not None, recommend_ready=request.app.state.recommend is not None)

    return router
