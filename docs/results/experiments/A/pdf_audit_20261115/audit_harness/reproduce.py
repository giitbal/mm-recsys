import json
import time
from pathlib import Path
from src.common.config import load_config
from src.common.artifacts import file_hash
from src.simulator.generate import generate

started = time.perf_counter()
cfg = load_config()
target = Path('.team/pdf-audit-20261115/reproduced-full')
original = json.loads(Path('data/full-v44/split_manifest.json').read_text())
actual = generate(cfg, target)
checks = {name:actual['file_hashes'].get(name)==digest for name,digest in original['file_hashes'].items()}
result = dict(status='PASS' if all(checks.values()) and actual['generation_fingerprint']==original['generation_fingerprint'] else 'FAIL',
    elapsed_seconds=time.perf_counter()-started, counts=actual['counts'], checks=checks,
    fingerprint=actual['generation_fingerprint'], source_sha256=file_hash(Path('src/simulator/generate.py')),
    scope='Independent regeneration from empty audit directory, current source, original full recipe; no model retraining')
Path('docs/results/experiments/A/pdf_audit_20261115/data_reproduction.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
