"""Bounded synthetic preflight failure-report probe; never mutates trial inputs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

PROJECT = Path('/workspace/sites/bos-original-refined')
TRIAL = Path('/workspace/scratch/c7b51e996a9f/tmp/a07_full_transfer_1')
OUT = Path('/workspace/scratch/c7b51e996a9f/tmp/a07_missing_media_preflight_probe.json')
sys.path.insert(0, str(PROJECT))
sys.path.append('/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages')
expected = json.loads((TRIAL / 'expected.json').read_text())
origin = Path(expected['origin']['database'])
assert origin.is_relative_to(TRIAL)
original_hash = hashlib.sha256(origin.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='a07_missing_media_') as raw:
    work = Path(raw)
    snapshot = work / 'synthetic.snapshot.sqlite3'
    media = work / 'media'
    shutil.copyfile(origin, snapshot)
    shutil.copytree(TRIAL / 'source-media', media)
    path = media / expected['chat']['relative_path']
    assert path.is_relative_to(media)
    path.unlink()
    copy_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings', BOS_VERIFY_DB='sqlite',
                      BOS_TEST_DB_NAME=':memory:', BOS_TEST_MEDIA=str(media))
    import django
    django.setup()
    from scripts.preflight_data import inspect_data
    try:
        report = inspect_data(snapshot, media)
        result = {'returned_report': True, 'can_migrate': report.get('can_migrate'),
                  'findings': report.get('findings')}
    except Exception as error:
        result = {'returned_report': False, 'error_type': type(error).__name__}
    result['trial_source_unchanged'] = hashlib.sha256(origin.read_bytes()).hexdigest() == original_hash
    result['probe_snapshot_unchanged'] = hashlib.sha256(snapshot.read_bytes()).hexdigest() == copy_hash
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
