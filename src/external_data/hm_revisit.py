"""Controlled H&M ablations on the unchanged v1 cohort, catalog and time splits."""
from __future__ import annotations

from collections.abc import Iterable
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

from src.common.artifacts import file_hash, fingerprint, write_json
from src.external_data.hm_evaluate import metrics, rank, ranking_inputs
from src.recommendation.candidate import ExactCandidate, dot_scores, top_indices
from src.recommendation.datasets import read_data
from src.recommendation.deepfm import DeepFM
from src.recommendation.eval_candidate import Evaluation
from src.recommendation.features import ITEM_FIELDS, ItemTable
from src.recommendation.two_tower import TwoTower
from src.recommendation.index import load_index
from src.recommendation.ranking_features import RankingEncoder, DENSE_FIELDS
from src.recommendation.reranking import RankedItem, Reranker
from src.recommendation.train_two_tower import load_bundle, train


def configuration(spec: dict) -> dict:
    source = Path(spec['source_work'])
    cfg = copy.deepcopy(json.loads((source / 'hm_models/two_tower/external_config.json').read_text())['config'])
    cfg['recommend']['candidate'].update(epochs=spec['candidate_epochs'], patience=spec['candidate_patience'], threads=spec['threads'])
    cfg['paths'].update(model_dir=str(Path(spec['work_dir']) / 'models'), results_dir=spec['results_dir'])
    return cfg


def counts_before(chunks: Iterable[pd.DataFrame], ids: list[str], cutoff: pd.Timestamp, windows: list[int]) -> np.ndarray:
    """Fit all popularity variants strictly on train; never update on valid/test."""
    result = np.zeros((len(windows), len(ids)), np.int64)
    positions = pd.Index(ids)
    for chunk in chunks:
        days = pd.to_datetime(chunk.t_dat, utc=True)
        before = days < cutoff
        for j, window in enumerate(windows):
            keep = before & ((days >= cutoff - pd.Timedelta(days=window)) if window else True)
            counts = ('HM-' + chunk.loc[keep, 'article_id']).value_counts()
            rows = positions.get_indexer(counts.index)
            if (rows < 0).any(): raise ValueError('unknown transaction product')
            result[j, rows] += counts.to_numpy()
    return result


def prepare(spec: dict, cfg: dict) -> None:
    work, results = Path(spec['work_dir']), Path(spec['results_dir'])
    source = Path(spec['source_work']) / 'hm_raw/transactions_train.csv'
    expected = json.loads((Path(spec['source_results']) / 'hm_data.json').read_text())['source_members']['transactions_train.csv']['sha256']
    if file_hash(source) != expected: raise ValueError('changed raw transaction source')
    data = read_data(cfg['paths']['data_dir'], 'valid')
    ids = ['<PAD>'] + sorted(data['products'].product_id.tolist())
    cutoff = pd.Timestamp(data['manifest']['boundaries']['train']['end'])
    chunks = pd.read_csv(source, usecols=['t_dat', 'article_id'], dtype={'article_id': str}, chunksize=500000)
    counts = counts_before(chunks, ids, cutoff, spec['popularity_windows_days'])
    np.save(work / 'population_counts.npy', counts)
    write_json(results / 'population.json', dict(status='PASS', source_sha256=expected,
        train_cutoff=str(cutoff), windows_days=spec['popularity_windows_days'],
        transactions=counts.sum(axis=1).tolist(), products_observed=(counts > 0).sum(axis=1).tolist(),
        counts_sha256=file_hash(work / 'population_counts.npy'), ids_fingerprint=fingerprint(ids),
        fit_scope='all source customers, train only; no valid/test population statistics'))


def population(spec: dict, table: ItemTable) -> np.ndarray:
    work, results = Path(spec['work_dir']), Path(spec['results_dir'])
    record = json.loads((results / 'population.json').read_text())
    if file_hash(work / 'population_counts.npy') != record['counts_sha256'] or fingerprint(table.ids) != record['ids_fingerprint']:
        raise ValueError('population cache/ID mismatch')
    return np.load(work / 'population_counts.npy')


def exact_lists(model: TwoTower, table: ItemTable, evaluation: Evaluation) -> list[list[str]]:
    reference = ExactCandidate(model, table, evaluation.eligible, 512)
    ranked: list[list[str]] = []
    for start in range(0, len(evaluation.contexts), 64):
        scores = dot_scores(reference.user_vectors(evaluation.contexts[start:start + 64]), reference.vectors)
        ranked.extend(table.public_ids(top_indices(row, evaluation.eligible)) for row in scores)
    return ranked


def hybrid_lists(neural: list[list[str]], pop: np.ndarray, evaluation: Evaluation,
                 weight: float, constant: float) -> list[list[str]]:
    """Weighted reciprocal ranks; all eligible items stay in the candidate universe."""
    if not 0 <= weight <= 1 or constant <= 0: raise ValueError('invalid fusion weights')
    eligible, table = evaluation.eligible, evaluation.table
    pop_order = np.lexsort((eligible, -pop[eligible]))
    prior = np.zeros(len(table.ids), np.float32)
    prior[eligible[pop_order]] = 1 / (constant + np.arange(1, len(eligible) + 1))
    result = []
    for row in neural:
        scores = (1 - weight) * prior.copy()
        indices = np.array([table.id_to_index[pid] for pid in row])
        scores[indices] += weight / (constant + np.arange(1, len(row) + 1))
        result.append(table.public_ids(top_indices(scores[eligible], eligible)))
    return result


def summarize(rows: list[list[str]], evaluation: Evaluation) -> dict:
    return dict(candidate=evaluation.measure(rows), ranking=metrics(rows, evaluation))


def rerank_blend(candidates: list[list[str]], learned: list[list[str]], weight: float,
                 evaluation: Evaluation, cfg: dict, products: pd.DataFrame, pop: np.ndarray) -> tuple[list[list[str]], dict]:
    if not 0 <= weight <= 1: raise ValueError('invalid ranking weight')
    reranker = Reranker(cfg, products)
    fallback = dict(zip(evaluation.table.ids[1:], pop[1:].astype(float).tolist()))
    output, details = [], []
    rng = np.random.default_rng(cfg['seed'])
    for row, deep, context in zip(candidates, learned, evaluation.contexts):
        positions = {pid: i for i, pid in enumerate(deep)}
        items = [RankedItem(pid, (1 - weight) * (1 - i / len(row)) + weight * (1 - positions[pid] / len(row)),
                            reason='H&M train 인기도·Two-Tower·구매 선호') for i, pid in enumerate(row)]
        final, detail = reranker.run(items, 50, evaluation.cutoff, context.history_count, fallback, {}, lambda pid: pid, rng)
        output.append([item.product_id for item in final]); details.append(detail)
    return output, dict(violating_users=sum(bool(d['violations']) for d in details),
        infeasible_diversity_users=sum(not d['diversity_feasible_for_returned'] for d in details))


def load_ranker(spec: dict, cfg: dict) -> tuple[DeepFM, RankingEncoder]:
    root = Path(spec['source_work']) / 'hm_models'
    original = json.loads((Path(spec['source_results']) / 'hm_recommendation.json').read_text())
    if file_hash(root / 'purchase_deepfm.pt') != original['model_hashes']['purchase_deepfm']:
        raise ValueError('changed frozen purchase model')
    encoder = RankingEncoder.from_dict(json.loads((root / 'purchase_features.json').read_text()))
    model = DeepFM(encoder.cardinalities, len(DENSE_FIELDS), cfg['recommend']['ranking'])
    model.load_state_dict(torch.load(root / 'purchase_deepfm.pt', map_location='cpu', weights_only=True))
    return model.eval(), encoder


def diagnostic(data: dict, evaluation: Evaluation, table: ItemTable) -> dict:
    eligible_ids = set(table.public_ids(evaluation.eligible))
    observed = set(data['train'].product_id)
    train_products = data['products'][data['products'].product_id.isin(eligible_ids)]
    features = [*ITEM_FIELDS, 'price']
    truth_size = sum(len(t) for t in evaluation.truth.values())
    return dict(train_events=len(data['train']), train_products=len(observed),
        eligible_products=len(eligible_ids), unobserved_eligible_products=len(eligible_ids - observed),
        indistinguishable_metadata_products=int(train_products.duplicated(features, keep=False).sum()),
        distinct_metadata_vectors=len(train_products.drop_duplicates(features)),
        train_brand_values=int(data['products'].brand.nunique()),
        valid_users=len(evaluation.user_ids), valid_truth_items=truth_size,
        valid_truth_unobserved_in_cohort=sum(len(t - observed) for t in evaluation.truth.values()),
        unavailable_macro_fraction=float(np.mean([len(t - eligible_ids) / len(t) for t in evaluation.truth.values()])),
        no_history_users=sum(c.history_count == 0 for c in evaluation.contexts),
        history_count_median=float(np.median([c.history_count for c in evaluation.contexts])),
        horizon_days=(data['valid'].timestamp.max() - evaluation.cutoff).total_seconds() / 86400,
        limitations=['item name, images and product identity not used by metadata Two-Tower',
                    'single-brand source and unknown customer demographics',
                    '1:4 random unobserved items are not observed non-purchases',
                    'fixed-origin multi-month forecast without within-period user updates'])


def dependencies(spec: dict) -> dict:
    work, source = Path(spec['work_dir']), Path(spec['source_work'])
    names = [work / 'models/two_tower/two_tower.pt', work / 'population_counts.npy',
             source / 'hm_models/purchase_deepfm.pt', source / 'hm_models/purchase_features.json',
             source / 'hm_models/two_tower/two_tower.pt', source / 'hm/split_manifest.json',
             source / 'hm_models/two_tower/external_config.json']
    return {str(p): file_hash(p) for p in names}


def evaluate(spec: dict, cfg: dict, split: str) -> None:
    work, results = Path(spec['work_dir']), Path(spec['results_dir'])
    if (results / 'test.json').exists(): raise ValueError('test already evaluated; preserve frozen results')
    choice_path = results / 'selection.json'
    if split == 'test':
        selection = json.loads(choice_path.read_text())
        source_hashes = {str(p): file_hash(p) for p in sorted(Path('src').rglob('*.py'))}
        if selection['spec_fingerprint'] != fingerprint(spec) or selection['source_hashes'] != source_hashes or selection['dependencies'] != dependencies(spec):
            raise ValueError('experiment changed after valid selection')
    elif choice_path.exists():
        raise ValueError('valid selection already frozen; use a new version')
    data = read_data(cfg['paths']['data_dir'], split)
    model, encoder, table, meta = load_bundle(work / 'models/two_tower', data, cfg)
    evaluation = Evaluation(data, encoder, table, cfg, split)
    pop = population(spec, table)
    learned = exact_lists(model, table, evaluation)
    variants = {}
    for j, window in enumerate(spec['popularity_windows_days']):
        rows = table.public_ids(top_indices(pop[j, evaluation.eligible], evaluation.eligible))
        variants[str(window)] = summarize([rows] * len(evaluation.user_ids), evaluation)
    if split == 'valid':
        window = max(spec['popularity_windows_days'], key=lambda w: variants[str(w)]['candidate']['recall_at_300'])
        selected_pop = pop[spec['popularity_windows_days'].index(window)]
        ablations = []
        for weight in spec['neural_weights']:
            rows = hybrid_lists(learned, selected_pop, evaluation, weight, spec['rrf_constant'])
            ablations.append(dict(neural_weight=weight, metrics=summarize(rows, evaluation)))
        chosen = max(ablations, key=lambda a: a['metrics']['candidate']['recall_at_300'])
        neural_weight = chosen['neural_weight']
    else:
        window, neural_weight = selection['window_days'], selection['neural_weight']
        selected_pop = pop[spec['popularity_windows_days'].index(window)]
    candidates = hybrid_lists(learned, selected_pop, evaluation, neural_weight, spec['rrf_constant'])
    ranker, rank_encoder = load_ranker(spec, cfg)
    inputs = ranking_inputs(candidates, evaluation, data, rank_encoder)
    deep_ranked, _ = rank(ranker, inputs, candidates, 512)
    if split == 'valid':
        rank_ablations = []
        for weight in spec['ranking_weights']:
            final, details = rerank_blend(candidates, deep_ranked, weight, evaluation, cfg, data['products'], selected_pop)
            rank_ablations.append(dict(deepfm_weight=weight, metrics=metrics(final, evaluation), diagnostics=details))
        selected_rank = max(rank_ablations, key=lambda a: a['metrics']['ndcg_at_50'])
        ranking_weight = selected_rank['deepfm_weight']
        original_cfg = json.loads((Path(spec['source_work']) / 'hm_models/two_tower/external_config.json').read_text())['config']
        old, _, _, old_meta = load_bundle(Path(spec['source_work']) / 'hm_models/two_tower', data, original_cfg)
        old_index, _ = load_index(Path(spec['source_work']) / 'hm_models/two_tower', table, old_meta)
        ann_comparison = evaluation.ann_metrics(old, old_index)
        write_json(results / 'diagnosis.json', dict(data=diagnostic(data, evaluation, table), original_ann_comparison=ann_comparison))
        selection = dict(status='FROZEN', window_days=window, neural_weight=neural_weight, deepfm_weight=ranking_weight,
            candidate_selection='valid macro Recall@300', rank_selection='valid reranked NDCG@50',
            candidate_ablations=ablations, ranking_ablations=rank_ablations,
            spec_fingerprint=fingerprint(spec), dependencies=dependencies(spec),
            source_hashes={str(p): file_hash(p) for p in sorted(Path('src').rglob('*.py'))},
            data_fingerprint=data['manifest']['generation_fingerprint'],
            note='v1 test was previously inspected; v2 is a valid-selected exploratory follow-up, not an untouched holdout')
        write_json(choice_path, selection)
    else:
        ranking_weight = selection['deepfm_weight']
    final, details = rerank_blend(candidates, deep_ranked, ranking_weight, evaluation, cfg, data['products'], selected_pop)
    write_json(results / f'{split}.json', dict(status='PASS', acceptance='UNMEASURED', split=split,
        population_baselines=variants, cohort_popularity=evaluation.baseline_metrics()['train_popularity'],
        neural_exact=summarize(learned, evaluation), hybrid=summarize(candidates, evaluation),
        purchase_deepfm=metrics(deep_ranked, evaluation), final=metrics(final, evaluation), reranking=details,
        chosen=dict(window_days=window, neural_weight=neural_weight, deepfm_weight=ranking_weight),
        data_fingerprint=data['manifest']['generation_fingerprint'], contract=evaluation.contract(),
        retrieval='exact metadata Two-Tower plus full train-popularity rank fusion; HNSW latency not measured',
        ranker='v1 purchase-preference DeepFM reused unchanged; no claim of new CTR/CVR learning',
        test_scope='same previously reported v1 holdout; exploratory follow-up',
        model_sha256=file_hash(work / 'models/two_tower/two_tower.pt'), dependencies=dependencies(spec)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/external_hm_v2.yaml')
    parser.add_argument('--task', choices=['prepare', 'train', 'valid', 'test', 'all'], default='all')
    args = parser.parse_args()
    spec = yaml.safe_load(Path(args.config).read_text())
    work, results = Path(spec['work_dir']), Path(spec['results_dir'])
    work.mkdir(parents=True, exist_ok=True); results.mkdir(parents=True, exist_ok=True)
    identity = work / 'experiment.json'
    if identity.exists() and json.loads(identity.read_text()) != spec: raise ValueError('changed experiment; use new directories')
    write_json(identity, spec)
    cfg = configuration(spec); torch.set_num_threads(spec['threads'])
    for task in (['prepare', 'train', 'valid', 'test'] if args.task == 'all' else [args.task]):
        print(f'[H&M 재검증] {task} 시작', flush=True)
        if task == 'prepare': prepare(spec, cfg)
        elif task == 'train':
            bundle = work / 'models/two_tower'
            if bundle.exists():
                load_bundle(bundle, read_data(cfg['paths']['data_dir'], 'valid'), cfg)
            else: train(cfg, results / 'candidate_training.json', bundle)
        else: evaluate(spec, cfg, task)
        print(f'[H&M 재검증] {task} 완료', flush=True)


if __name__ == '__main__':
    main()
