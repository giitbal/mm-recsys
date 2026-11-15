"""Frozen CLIP on unencrypted official Category/Attribute splits."""
from __future__ import annotations

import hashlib
import io
import time
from zipfile import ZipFile

import numpy as np
from PIL import Image

from src.common.artifacts import file_hash, fingerprint, write_json
from src.common.config import load_config
from src.evaluation.metrics import mrr, ndcg_at_k
from src.external_data.io import member_text, paths
from src.search.encoder import CLIPEncoder

PREFIX = 'Category and Attribute Prediction Benchmark/'


def annotation_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    rows = [line.split() for line in lines[2:] if line.strip()]
    if int(lines[0]) != len(rows): raise ValueError('annotation count mismatch')
    return rows


def run(spec: dict) -> dict:
    source, work, results = paths(spec)
    s = spec['deepfashion']
    label_text = member_text(source / s['categories_archive'], PREFIX + 'Anno_coarse/list_category_img.txt')
    split_text = member_text(source / s['partitions_archive'], PREFIX + 'Eval/list_eval_partition.txt')
    class_text = member_text(source / s['classes_archive'], PREFIX + 'Anno_coarse/list_category_cloth.txt')
    labels = {name: int(label) - 1 for name, label in annotation_rows(label_text)}
    partitions = annotation_rows(split_text)
    classes = [' '.join(row[:-1]).replace('_', ' ') for row in annotation_rows(class_text)]
    if len(labels) != len(partitions) or {r[0] for r in partitions} != set(labels):
        raise ValueError('split/label coverage mismatch')
    rng = np.random.default_rng(spec['seed'])
    selected = {}
    for split, limit in [('train', s['gallery_images']), ('val', s['queries_per_split']), ('test', s['queries_per_split'])]:
        pool_names = np.array(sorted(name for name, part in partitions if part == split))
        selected[split] = sorted(rng.choice(pool_names, min(limit, len(pool_names)), replace=False).tolist())
    cfg = load_config(); cfg['search'].update(batch_size=s['batch_size'], torch_threads=s['threads'])
    encoder = CLIPEncoder(cfg)
    prompts = [f'a photo of a {name}' for name in classes]
    text_vectors = encoder.encode_texts(prompts)
    vectors, digests, elapsed = {}, {}, {}
    with ZipFile(source / s['images_archive']) as archive:
        all_names = set(archive.namelist())
        if not set(labels).issubset(all_names): raise ValueError('missing annotated images')
        for split, names in selected.items():
            started = time.perf_counter(); chunks = []; hashes = []
            for start in range(0, len(names), s['batch_size']):
                images = []
                try:
                    for name in names[start:start + s['batch_size']]:
                        raw = archive.read(name)
                        hashes.append(hashlib.sha256(raw).hexdigest())
                        with Image.open(io.BytesIO(raw)) as image:
                            images.append(image.convert('RGB').copy())
                    chunks.append(encoder.encode_images(images))
                finally:
                    for image in images: image.close()
            vectors[split] = np.concatenate(chunks); digests[split] = hashes
            elapsed[split] = time.perf_counter() - started
    gallery_labels = np.array([labels[n] for n in selected['train']])
    train_labels = [labels[name] for name, split in partitions if split == 'train']
    majority = int(np.bincount(train_labels, minlength=len(classes)).argmax())
    gallery_hashes = np.array(digests['train'])
    measured = {}
    for split in ('val', 'test'):
        truth = np.array([labels[n] for n in selected[split]])
        scores = vectors[split] @ text_vectors.T
        order = np.argsort(-scores, axis=1, kind='stable')
        ranked_classes = [[str(v) for v in row[:10]] for row in order]
        class_truth = [{str(v)} for v in truth]
        image_scores = vectors[split] @ vectors['train'].T
        image_ranked, image_truth, duplicate_pairs = [], [], 0
        for i, label in enumerate(truth):
            duplicates = gallery_hashes == digests[split][i]
            duplicate_pairs += int(duplicates.sum())
            allowed = np.flatnonzero(~duplicates)
            ranked = allowed[np.argsort(-image_scores[i, allowed], kind='stable')[:10]]
            image_ranked.append([selected['train'][j] for j in ranked])
            image_truth.append({selected['train'][j] for j in allowed if gallery_labels[j] == label})
        measured[split] = dict(queries=len(truth), zero_shot_category_accuracy=float(np.mean(order[:, 0] == truth)),
            train_majority_category_accuracy=float(np.mean(truth == majority)),
            macro_category_accuracy=float(np.mean([np.mean(order[truth == c, 0] == c) for c in np.unique(truth)])),
            zero_shot_category_top5=float(np.mean((order[:, :5] == truth[:, None]).any(axis=1))),
            class_retrieval_mrr_at_10=mrr(ranked_classes, class_truth),
            class_retrieval_ndcg_at_10=float(np.mean([ndcg_at_k(r, t, 10) for r, t in zip(ranked_classes, class_truth)])),
            image_category_mrr_at_10=mrr(image_ranked, image_truth),
            image_category_ndcg_at_10=float(np.mean([ndcg_at_k(r, t, 10) for r, t in zip(image_ranked, image_truth)])),
            queries_without_relevant_gallery=sum(not t for t in image_truth), exact_duplicate_pairs_excluded=duplicate_pairs,
            embedding_seconds=elapsed[split])
    local = work / 'deepfashion'; local.mkdir(parents=True, exist_ok=True)
    for split in selected:
        np.save(local / f'{split}.npy', vectors[split])
    write_json(local / 'selection.json', dict(names=selected, image_sha256=digests, prompts=prompts))
    report = dict(status='PASS', acceptance='UNMEASURED', benchmark='DeepFashion Category and Attribute Prediction',
        scope='fixed seed image sample from official splits; category relevance, not instance identity or PDF product-search acceptance',
        official_counts={part: sum(p == part for _, p in partitions) for part in ('train', 'val', 'test')},
        counts={k: len(v) for k, v in selected.items()}, classes=len(classes), model=encoder.metadata,
        selection_fingerprint=fingerprint(selected), content_fingerprint=fingerprint(digests),
        source_hashes=dict(images_zip=file_hash(source / s['images_archive']),
            labels=hashlib.sha256(label_text.encode()).hexdigest(), partitions=hashlib.sha256(split_text.encode()).hexdigest(),
            classes=hashlib.sha256(class_text.encode()).hexdigest()),
        metrics=measured, training='none; frozen checkpoint, fixed prompts, no test-driven selection',
        limitations=['category labels only; fine-grained attributes not evaluated',
                    'exact duplicates excluded; perceptual near duplicates not audited',
                    'no In-shop or Consumer-to-shop passwords required', 'batch encoding time is not API latency'])
    write_json(results / 'deepfashion.json', report)
    return report
