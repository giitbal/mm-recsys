from __future__ import annotations

import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from src.common.config import require_image_recipe
from src.simulator.illustrations import illustration


def leaves(cfg: dict) -> list[tuple[str, str, str]]:
    return [(l1, l2, l3) for l1, mids in cfg['simulator']['taxonomy'].items()
            for l2, values in mids.items() for l3 in values]


def render_product(row: dict, cfg: dict, variant: int = 0) -> Image.Image:
    require_image_recipe(cfg['simulator'])
    return illustration(row, cfg, variant)


def make_catalog(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    sim = cfg['simulator']; n = sim['n_products']; taxonomy = leaves(cfg)
    leaf_ids = np.arange(n) % len(taxonomy)
    rng.shuffle(leaf_ids)
    brands, colors, styles = sim['brands'], list(sim['colors']), sim['styles']
    brand_ids = rng.integers(len(brands),size=n)
    color_ids = rng.integers(len(colors),size=n)
    style_ids = rng.integers(len(styles),size=n)
    ref = pd.Timestamp(sim['reference_time'])
    created = ref - pd.to_timedelta(rng.integers(35,120,size=n),unit='D')
    new = rng.choice(n,size=int(n*sim['new_item_ratio']),replace=False)
    created = pd.Series(created)
    created.iloc[new] = ref-pd.to_timedelta(rng.integers(0,7,size=len(new)),unit='D')
    rows=[]
    for i in range(n):
        l1,l2,l3 = taxonomy[leaf_ids[i]]
        low,high = sim['category_price_ranges'][l1]
        price = int(rng.uniform(low,high)//1000*1000)
        color,brand,style=colors[color_ids[i]],brands[brand_ids[i]],styles[style_ids[i]]
        rows.append({'product_id':f'P{i+1:06d}','name':f'{color} {style} {l3}',
                     'category_l1':l1,'category_l2':l2,'category_l3':l3,
                     'brand':brand,'color':color,'style':style,
                     'attributes':json.dumps({'style':style},sort_keys=True),
                     'price':price,'created_at':created.iloc[i],
                     'image_path':f'images/P{i+1:06d}.jpg',
                     'description_en':f'a photo of a {color} {style} {l3}'})
    return pd.DataFrame(rows)


def write_images(products: pd.DataFrame, cfg: dict, data_dir: Path) -> None:
    folder=data_dir/'images';folder.mkdir(parents=True,exist_ok=True)
    hashes=[]
    for i,row in enumerate(products.to_dict('records')):
        path=data_dir/row['image_path']
        render_product(row,cfg,i%cfg['simulator']['image_variants']).save(path,quality=85)
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    products['image_sha256']=hashes
    products['visual_group']=hashes
