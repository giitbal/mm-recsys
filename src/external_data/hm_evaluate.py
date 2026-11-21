"""H&M Two-Tower -> purchase-preference DeepFM -> existing reranker.

Sampled unobserved items are NOT unclicked impressions. This experiment never
exports its ranker as a CTR/CVR serving model.
"""
from __future__ import annotations

import copy
import json
import platform
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import torch

from src.common.artifacts import file_hash, fingerprint, write_json
from src.common.config import load_config
from src.common.seed import set_seed
from src.evaluation.metrics import ndcg_at_k, hit_rate_at_k
from src.external_data.io import paths
from src.recommendation.candidate import FaissCandidate, top_indices
from src.recommendation.datasets import TrainingDataset, read_data
from src.recommendation.deepfm import DeepFM
from src.recommendation.eval_candidate import Evaluation
from src.recommendation.index import load_index
from src.recommendation.features import ItemTable
from src.recommendation.ranking_features import DENSE_FIELDS, HistoryIndex, RankingEncoder
from src.recommendation.reranking import RankedItem, Reranker
from src.recommendation.train_two_tower import train, load_bundle
from src.recommendation.two_tower import TwoTower

if TYPE_CHECKING:
    import faiss


def metrics(ranked: list[list[str]], evaluation: Evaluation) -> dict:
    truths = [evaluation.truth[u] for u in evaluation.user_ids]
    if not truths: raise ValueError('no evaluation targets')
    return dict(users=len(truths), empty_target_users=evaluation.empty_users,
        hit_rate_at_50=float(np.mean([hit_rate_at_k(r, t, 50) for r, t in zip(ranked, truths)])),
        ndcg_at_50=float(np.mean([ndcg_at_k(r, t, 50) for r, t in zip(ranked, truths)])),
        coverage_at_50=len({p for row in ranked for p in row[:50]}) / (len(evaluation.table.ids) - 1))


def candidate_lists(model: TwoTower, table: ItemTable, index: faiss.Index, evaluation: Evaluation, batch_size: int, diagnostics: dict) -> list[list[str]]:
    retriever = FaissCandidate(model, table, evaluation.eligible, index)
    ranked = []
    for start in range(0, len(evaluation.contexts), batch_size):
        ranked.extend(retriever.search(retriever.user_vectors(evaluation.contexts[start:start + batch_size])))
    diagnostics.update(queries=len(ranked), exact_refill_queries=retriever.exact_refill_queries,
                       policy='HNSW; exhaustive same-vector full-catalog completion only if ANN cannot supply required count')
    return ranked


def ranking_inputs(ranked: list[list[str]], evaluation: Evaluation, data: dict, encoder: RankingEncoder) -> tuple[np.ndarray, np.ndarray]:
    history_events = data['train'] if evaluation.split == 'valid' else pd.concat([data['train'], data['valid']], ignore_index=True)
    history = HistoryIndex(history_events, evaluation.table, data['train'])
    labels = pd.DataFrame([(uid, pid, evaluation.cutoff) for uid, row in zip(evaluation.user_ids, ranked) for pid in row],
                          columns=['user_id', 'product_id', 'exposed_at'])
    # exposed_at is an existing feature API field, not an assertion of real exposure.
    return encoder.transform(labels, data['users'], evaluation.table, history, freeze_at=evaluation.cutoff)


def rank(model: DeepFM, inputs: tuple[np.ndarray, np.ndarray], candidates: list[list[str]], batch_size: int) -> tuple[list[list[str]], list[np.ndarray]]:
    sparse, dense = inputs
    scores = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(sparse), batch_size):
            value = model(torch.from_numpy(sparse[start:start + batch_size]), torch.from_numpy(dense[start:start + batch_size]))[:, 0]
            scores.append(value.numpy())
    values = np.concatenate(scores)
    result, row_scores, offset = [], [], 0
    for row in candidates:
        block = values[offset:offset + len(row)]; offset += len(row)
        order = np.lexsort((np.array(row), -block))
        result.append([row[i] for i in order]); row_scores.append(block)
    return result, row_scores


def run(spec: dict) -> dict:
    _, work, results = paths(spec)
    s = spec['hm']; cfg = load_config(); cfg['seed'] = spec['seed']
    cfg['paths'].update(data_dir=str(work / 'hm'), model_dir=str(work / 'hm_models'), results_dir=str(results))
    cfg['recommend']['candidate'].update(epochs=s['candidate_epochs'], threads=s['threads'], batch_size=s['batch_size'])
    cfg['recommend']['ranking'].update(epochs=s['ranking_epochs'], threads=s['threads'])
    completed = results / 'hm_recommendation.json'
    if completed.exists():
        previous = json.loads(completed.read_text())
        frozen = json.loads((results / 'hm_selection.json').read_text())
        if frozen['config_fingerprint'] != fingerprint(cfg) or frozen['runner_sha256'] != file_hash(Path(__file__)):
            raise ValueError('frozen experiment changed; use a new work/results version')
        for key, path in {'two_tower': work / 'hm_models/two_tower/two_tower.pt',
                          'purchase_deepfm': work / 'hm_models/purchase_deepfm.pt'}.items():
            if file_hash(path) != previous['model_hashes'][key]: raise ValueError('changed frozen checkpoint')
        read_data(work / 'hm', 'test')
        return previous
    set_seed(spec['seed']); torch.set_num_threads(s['threads'])
    bundle = work / 'hm_models/two_tower'
    selection_path = bundle / 'external_config.json'
    if bundle.exists():
        if not selection_path.exists() or json.loads(selection_path.read_text())['fingerprint'] != fingerprint(cfg):
            raise ValueError('unregistered or changed external training config; use new work_dir')
    else:
        train(cfg, results / 'hm_candidate_training.json', bundle)
        write_json(selection_path, dict(fingerprint=fingerprint(cfg), config=cfg))
    data = read_data(work / 'hm', 'valid')
    candidate, metadata, table, bundle_meta = load_bundle(bundle, data, cfg)
    index, _ = load_index(bundle, table, bundle_meta)
    validation = Evaluation(data, metadata, table, cfg, 'valid')
    valid_retrieval: dict = {}
    valid_candidates = candidate_lists(candidate, table, index, validation, s['batch_size'], valid_retrieval)
    set_seed(spec['seed'] + 100)
    dataset = TrainingDataset(data['train'], data['users'], metadata, table, cfg)
    event_users = data['train'].set_index('event_id').user_id
    labels = pd.DataFrame(dict(user_id=np.repeat(event_users.loc[dataset.event_ids].to_numpy(), 5),
        product_id=np.array(table.ids)[dataset.items.numpy().reshape(-1)],
        exposed_at=pd.to_datetime(np.repeat(dataset.timestamps, 5), utc=True)))
    targets = torch.from_numpy(np.tile(np.array([1, 0, 0, 0, 0], np.float32), len(dataset)))
    encoder = RankingEncoder(metadata, np.zeros(len(DENSE_FIELDS), np.float32), np.ones(len(DENSE_FIELDS), np.float32), True)
    inputs = encoder.transform(labels, data['users'], table, HistoryIndex(data['train'], table), fit=True)
    valid_inputs = ranking_inputs(valid_candidates, validation, data, encoder)
    ranking = DeepFM(encoder.cardinalities, len(DENSE_FIELDS), cfg['recommend']['ranking'])
    optimizer = torch.optim.AdamW(ranking.parameters(), lr=cfg['recommend']['ranking']['learning_rate'],
                                 weight_decay=cfg['recommend']['ranking']['weight_decay'])
    sparse, dense = map(torch.from_numpy, inputs)
    generator = torch.Generator().manual_seed(spec['seed'])
    best, best_epoch, best_state, epochs = -1., 0, None, []
    for epoch in range(1, s['ranking_epochs'] + 1):
        ranking.train(); total = 0.
        order = torch.randperm(len(targets), generator=generator)
        for start in range(0, len(order), s['batch_size']):
            batch = order[start:start + s['batch_size']]
            optimizer.zero_grad(set_to_none=True)
            logits = ranking(sparse[batch], dense[batch])[:, 0]
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, targets[batch])
            if not torch.isfinite(loss): raise ValueError('nonfinite purchase ranking loss')
            loss.backward()
            grad = torch.nn.utils.clip_grad_norm_(ranking.parameters(), cfg['recommend']['ranking']['max_grad_norm'])
            if not torch.isfinite(grad): raise ValueError('nonfinite purchase ranking gradient')
            optimizer.step(); total += float(loss.detach()) * len(batch)
        ranked, _ = rank(ranking, valid_inputs, valid_candidates, s['batch_size'])
        measured = metrics(ranked, validation)
        epochs.append(dict(epoch=epoch, loss=total / len(targets), valid=measured))
        print(f"H&M purchase DeepFM epoch={epoch} valid NDCG@50={measured['ndcg_at_50']:.6f}", flush=True)
        if measured['ndcg_at_50'] > best:
            best, best_epoch, best_state = measured['ndcg_at_50'], epoch, copy.deepcopy(ranking.state_dict())
    if best_state is None: raise ValueError('ranking checkpoint not selected')
    ranking.load_state_dict(best_state)
    model_path = work / 'hm_models/purchase_deepfm.pt'
    torch.save(ranking.state_dict(), model_path)
    write_json(work / 'hm_models/purchase_features.json', encoder.to_dict())
    write_json(results / 'hm_selection.json', dict(status='FROZEN', candidate_model_sha256=file_hash(bundle / 'two_tower.pt'),
        purchase_model_sha256=file_hash(model_path), best_ranking_epoch=best_epoch, selection_metric='valid NDCG@50',
        config_fingerprint=fingerprint(cfg), data_fingerprint=data['manifest']['generation_fingerprint'], epochs=epochs,
        runner_sha256=file_hash(Path(__file__)),
        objective='purchase vs random unobserved 1:4, not CTR/CVR; unused second DeepFM output'))
    # Only after both model choices are frozen is test loaded and evaluated.
    test_data = read_data(work / 'hm', 'test')
    test = Evaluation(test_data, metadata, table, cfg, 'test')
    measured_splits = {}
    reranker = Reranker(cfg, data['products'])
    for split, evaluation, current in [('valid', validation, data), ('test', test, test_data)]:
        retrieval = valid_retrieval if split == 'valid' else {}
        candidates = valid_candidates if split == 'valid' else candidate_lists(candidate, table, index, evaluation, s['batch_size'], retrieval)
        features = valid_inputs if split == 'valid' else ranking_inputs(candidates, evaluation, current, encoder)
        ranked, row_scores = rank(ranking, features, candidates, s['batch_size'])
        popularity = table.public_ids(top_indices(evaluation.baselines.popularity[evaluation.eligible], evaluation.eligible))
        final, diagnostics = [], []
        rng = np.random.default_rng(spec['seed'])
        fallback = dict(zip(table.ids[1:], evaluation.baselines.popularity[1:].tolist()))
        for row, scores, context in zip(candidates, row_scores, evaluation.contexts):
            items = [RankedItem(pid, float(score), reason='H&M 구매 선호도') for pid, score in zip(row, scores)]
            reranked, detail = reranker.run(items, 50, evaluation.cutoff, context.history_count, fallback, {}, lambda pid: pid, rng)
            final.append([item.product_id for item in reranked]); diagnostics.append(detail)
        measured_splits[split] = dict(candidate=evaluation.measure(candidates), retrieval=retrieval,
            stages={'popularity': metrics([popularity] * len(candidates), evaluation),
                    'two_tower_only': metrics(candidates, evaluation), 'purchase_deepfm': metrics(ranked, evaluation),
                    'reranked': metrics(final, evaluation)},
            reranking={'violating_users': sum(bool(d['violations']) for d in diagnostics),
                       'infeasible_diversity_users': sum(not d['diversity_feasible_for_returned'] for d in diagnostics),
                       'new_item_proxy_unavailable_users': sum(d['new_available'] == 0 for d in diagnostics),
                       'exploration_slots': cfg['recommend']['mab']['exploration_slots']})
    report = dict(status='PASS', acceptance='UNMEASURED', scope='predeclared user cohort; full cutoff-available source catalog',
        data_fingerprint=data['manifest']['generation_fingerprint'], counts=data['manifest']['counts'],
        model_hashes={'two_tower': file_hash(bundle / 'two_tower.pt'), 'purchase_deepfm': file_hash(model_path)},
        metrics=measured_splits, best_ranking_epoch=best_epoch,
        ctr_auc={'status': 'NOT_IDENTIFIABLE', 'reason': 'no impressions or unclicked exposure labels'},
        cvr_auc={'status': 'NOT_IDENTIFIABLE', 'reason': 'purchase-only source; no observed click denominator'},
        limitations=['sampled user cohort, not all H&M customers', 'static article snapshot and first-observation registration proxy',
                    'purchase preference ranker cannot be deployed as a CTR/CVR model',
                    'offline MAB has no counterfactual reward or online A/B evidence',
                    'new item means first observed purchase, not proven launch within seven days',
                    'full PDF synthetic quality and serving latency not re-established'],
        environment=dict(python=platform.python_version(), torch=torch.__version__, threads=torch.get_num_threads(), device='cpu'))
    write_json(results / 'hm_recommendation.json', report)
    return report
