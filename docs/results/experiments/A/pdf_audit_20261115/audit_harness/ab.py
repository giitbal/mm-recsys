from pathlib import Path
import shutil
from src.common.config import load_config
from src.common.artifacts import write_json
from src.evaluation.ab_test import run
from src.evaluation.verify_ab import verify

cfg = load_config()
cfg['paths']['model_dir'] = '.team/pdf-audit-20261115/serving_models'
cfg['paths']['results_dir'] = '.team/pdf-audit-20261115/runtime/full'
cfg['serving']['ab_test'].update(users_per_group=500, days=7)
out = Path('docs/results/experiments/A/pdf_audit_20261115/ab_test.json')
result = run(cfg, out)
write_json(out.with_name('ab_verification.json'), verify(out, cfg))
shutil.copyfile(out, Path(cfg['paths']['results_dir'])/'ab_test.json')
print(result['status'], result['inference']['ctr'], result['inference']['cvr'])
