"""Bounded archive reads and content identities for local research datasets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import yaml

from src.common.artifacts import file_hash, fingerprint, write_json


def load_spec(path: str) -> dict:
    spec = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    for key in ('source_dir', 'work_dir', 'results_dir'):
        if not isinstance(spec.get(key), str):
            raise ValueError(f'missing {key}')
    for section, keys in {'hm': ('user_limit', 'chunk_rows', 'candidate_epochs', 'ranking_epochs', 'batch_size', 'threads'),
                          'deepfashion': ('gallery_images', 'queries_per_split', 'batch_size', 'threads'),
                          'retailrocket': ('session_seconds',),
                          'calibration': ('pilot_products', 'pilot_users', 'pilot_events')}.items():
        if any(int(spec[section][key]) <= 0 for key in keys):
            raise ValueError(f'positive limits required: {section}')
    if not 0 <= spec['calibration']['preference_blend'] <= 1 or spec['retailrocket']['smoothing'] < 0:
        raise ValueError('invalid calibration/smoothing')
    return spec


def paths(spec: dict) -> tuple[Path, Path, Path]:
    return Path(spec['source_dir']), Path(spec['work_dir']), Path(spec['results_dir'])


def member_text(archive: Path, member: str) -> str:
    with ZipFile(archive) as z:
        if z.getinfo(member).file_size > 100_000_000:
            raise ValueError('annotation exceeds bounded text read')
        return z.read(member).decode('utf-8-sig')


def extract_member(archive: Path, member: str, target: Path) -> dict:
    """Caller supplies the target; never extract archive-controlled paths."""
    with ZipFile(archive) as z:
        info = z.getinfo(member)
        source = dict(archive=archive.name, member=member, crc32=info.CRC, bytes=info.file_size)
        marker = target.with_suffix(target.suffix + '.source.json')
        if target.exists():
            if not marker.exists():
                raise ValueError(f'unregistered existing file: {target}')
            record = json.loads(marker.read_text())
            if any(record.get(k) != v for k, v in source.items()) or file_hash(target) != record['sha256']:
                raise ValueError(f'changed source/cache: {target}; use a new work_dir')
            return record
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.partial')
        digest = hashlib.sha256()
        try:
            with z.open(member) as incoming, temporary.open('wb') as output:
                for block in iter(lambda: incoming.read(1024 * 1024), b''):
                    digest.update(block)
                    output.write(block)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        record = dict(source, sha256=digest.hexdigest())
        write_json(marker, record)
        return record


def inventory(spec: dict) -> dict:
    source, work, results = paths(spec)
    records = []
    for path in sorted(source.iterdir()):
        if not path.is_file() or ':Zone.Identifier' in path.name:
            continue
        row = dict(name=path.name, bytes=path.stat().st_size)
        if path.suffix == '.zip':
            with ZipFile(path) as z:
                members = z.infolist()
                row.update(entries=len(members), uncompressed_bytes=sum(i.file_size for i in members),
                           encrypted_entries=sum(bool(i.flag_bits & 1) for i in members),
                           csv_members=[i.filename for i in members if i.filename.endswith('.csv')],
                           directory_fingerprint=fingerprint([(i.filename, i.CRC, i.file_size) for i in members]))
        else:
            row['sha256'] = file_hash(path)
        records.append(row)
    identity = fingerprint(dict(config=spec, files=records))
    marker = work / 'identity.json'
    if marker.exists() and json.loads(marker.read_text())['identity'] != identity:
        raise ValueError('source/config changed; use new work_dir and results_dir')
    write_json(marker, dict(identity=identity, config=spec, files=records))
    report = dict(status='PASS', acceptance='UNMEASURED', identity=identity, files=records,
                  integrity='ZIP central directories only; consumed CSV members checked by CRC and SHA256; images decoded when evaluated')
    write_json(results / 'inventory.json', report)
    return report
