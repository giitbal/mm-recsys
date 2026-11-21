"""Shared identities and paths for the six predeclared external-data experiments."""
from pathlib import Path
import json
import yaml
from src.common.artifacts import file_hash, fingerprint, write_json


def plan(path: str | Path = 'config/external_expansion.yaml') -> tuple[dict, Path, Path]:
    spec=yaml.safe_load(Path(path).read_text())
    work, results=Path(spec['work_dir']),Path(spec['results_dir'])
    work.mkdir(parents=True,exist_ok=True);results.mkdir(parents=True,exist_ok=True)
    marker=work/'plan.json'
    if marker.exists() and json.loads(marker.read_text())!=spec:raise ValueError('changed experiment plan; choose new work/results paths')
    write_json(marker,spec)
    return spec,work,results


def frozen_sources() -> dict[str, str]:
    return {str(p):file_hash(p) for p in sorted(Path('src').rglob('*.py'))}
