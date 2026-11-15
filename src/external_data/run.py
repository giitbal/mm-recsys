"""Reproducible offline dataset use, without touching active serving artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout

from src.common.artifacts import file_hash, write_json
from src.external_data.io import inventory, load_spec, paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/external_data.yaml')
    parser.add_argument('--task', choices=['inventory', 'prepare-hm', 'retailrocket', 'deepfashion', 'hm', 'calibrate', 'verify', 'all'], default='all')
    args = parser.parse_args(); spec = load_spec(args.config)
    with redirect_stdout(sys.stderr):
        inventory(spec)
        from src.external_data import calibration, deepfashion, hm_evaluate, hm_prepare, retailrocket, verify
        tasks = {'prepare-hm': hm_prepare.prepare, 'retailrocket': retailrocket.run,
                 'deepfashion': deepfashion.run, 'hm': hm_evaluate.run, 'calibrate': calibration.run, 'verify': verify.run}
        selected = list(tasks) if args.task == 'all' else ([] if args.task == 'inventory' else [args.task])
        for task in selected:
            print(f'[외부 데이터] {task} 시작', flush=True)
            result = tasks[task](spec)
            print(f'[외부 데이터] {task} 완료 / 실행={result["status"]} / 최종 품질={result["acceptance"]}', flush=True)
    _, _, results = paths(spec)
    names = ['inventory', 'hm_data', 'retailrocket', 'deepfashion', 'hm_selection', 'hm_recommendation', 'calibration', 'verification']
    summary = dict(status='PASS', acceptance='UNMEASURED', task=args.task,
                   reports={name: dict(path=str(results / f'{name}.json'), sha256=file_hash(results / f'{name}.json'))
                            for name in names if (results / f'{name}.json').exists()})
    write_json(results / 'run.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
