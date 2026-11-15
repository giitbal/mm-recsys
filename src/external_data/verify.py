"""Check executed reports against frozen source, data and model artifacts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from src.common.artifacts import file_hash, fingerprint, write_json
from src.external_data.io import paths
from src.recommendation.datasets import read_data


def run(spec: dict) -> dict:
    _, work, results = paths(spec)
    names = ('inventory', 'hm_data', 'hm_candidate_training', 'hm_selection', 'hm_recommendation', 'retailrocket', 'deepfashion', 'calibration')
    reports = {name: json.loads((results / f'{name}.json').read_text()) for name in names}
    data = read_data(work / 'hm', 'test')
    hm, selection = reports['hm_recommendation'], reports['hm_selection']
    if hm['data_fingerprint'] != data['manifest']['generation_fingerprint'] or selection['data_fingerprint'] != hm['data_fingerprint']:
        raise ValueError('H&M report/data mismatch')
    if selection['runner_sha256'] != file_hash(Path('src/external_data/hm_evaluate.py')):
        raise ValueError('H&M runner changed after model selection')
    for name, path in {'two_tower': work / 'hm_models/two_tower/two_tower.pt', 'purchase_deepfm': work / 'hm_models/purchase_deepfm.pt'}.items():
        if file_hash(path) != hm['model_hashes'][name]: raise ValueError('model hash mismatch')
    for dataset, root in [('hm_data', work / 'hm_raw'), ('retailrocket', work / 'retailrocket_raw')]:
        for name, record in reports[dataset]['source_members'].items():
            if file_hash(root / name) != record['sha256']: raise ValueError('source member hash mismatch')
    if set(hm['metrics']['test']['stages']) != {'popularity', 'two_tower_only', 'purchase_deepfm', 'reranked'}:
        raise ValueError('missing multi-stage comparison')
    if hm['ctr_auc']['status'] != 'NOT_IDENTIFIABLE' or hm['cvr_auc']['status'] != 'NOT_IDENTIFIABLE':
        raise ValueError('purchase-only data must not be reported as impression CTR/CVR')
    for row in reports['retailrocket']['fitted_transitions'].values():
        if not np.isfinite(list(row.values())).all() or not np.isclose(sum(row.values()), 1):
            raise ValueError('invalid transition probabilities')
    clip = reports['deepfashion']
    if set(clip['metrics']) != {'val', 'test'} or clip['counts']['test'] != spec['deepfashion']['queries_per_split']:
        raise ValueError('incomplete CLIP evaluation')
    for name in ('hm_data', 'hm_recommendation', 'retailrocket', 'deepfashion', 'calibration'):
        if reports[name]['status'] != 'PASS' or reports[name]['acceptance'] != 'UNMEASURED':
            raise ValueError(f'invalid completion/acceptance separation: {name}')
    test = hm['metrics']['test']
    reference = dict(recall_at_300={'measured': test['candidate']['recall_at_300'], 'reference': .30})
    reference.update({key: {'measured': test['stages']['reranked'][key], 'reference': threshold}
                      for key, threshold in [('hit_rate_at_50', .20), ('ndcg_at_50', .08), ('coverage_at_50', .20)]})
    for value in reference.values(): value['meets_reference'] = value['measured'] >= value['reference']
    output = dict(status='PASS', acceptance='UNMEASURED', verified_purposes=3,
        repository_base=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        report_hashes={name: file_hash(results / f'{name}.json') for name in names},
        source_hashes={str(p): file_hash(p) for p in sorted(Path('src').rglob('*.py'))},
        config_fingerprint=fingerprint(spec),
        hm_pdf_reference_comparison=reference,
        reference_scope='descriptive only: H&M user cohort differs from synthetic full PDF protocol; not final acceptance',
        unmeasured=['all-customer H&M quality', 'full DeepFashion evaluation', 'real CTR/CVR and online A/B',
                    'calibrated full model quality, Docker latency and CT promotion'])
    write_json(results / 'verification.json', output)
    return output
