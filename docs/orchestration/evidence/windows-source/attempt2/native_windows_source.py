"""Bounded native Windows source identity proof; no app or database execution."""
import hashlib
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest
import uuid
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE / 'candidate-runtime'
OUT = BASE.parent / 'outputs/windows-source-evidence'
HEAD = '82beca6c14e097a31200068d72b15334c5bed319'
EXPECTED = 'ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5'
inventory = json.loads((BASE / 'live-audit/runtime-inventory.json').read_text(encoding='utf-8'))
OUT.mkdir(parents=True, exist_ok=True)

def verify_files():
    spellings, records = {}, []
    for entry in inventory:
        assert entry['mode'] in ('100644', '100755'), entry
        parts = entry['path'].split('/')
        for length in range(1, len(parts) + 1):
            spelling = '/'.join(parts[:length])
            assert spellings.setdefault(spelling.casefold(), spelling) == spelling, spelling
        file = ROOT / entry['path']
        assert file.is_file() and not file.is_symlink(), entry
        data = file.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        assert blob == entry['sha'] and len(data) == entry['size'], entry
        records.append({**entry, 'sha256': hashlib.sha256(data).hexdigest()})
    actual = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file())
    expected = sorted([e['path'] for e in inventory] + ['AGENTS.md'])
    assert actual == expected, {'missing': sorted(set(expected)-set(actual)), 'extra': sorted(set(actual)-set(expected))}
    assert all(not p.is_symlink() for p in ROOT.rglob('*'))
    return records

def known_digest(entries):
    h = hashlib.sha256()
    for name, data in entries:
        h.update(name.encode() + b'\0' + data + b'\0')
    return h.hexdigest()

started = time.monotonic()
assert os.name == 'nt' and platform.system() == 'Windows'
assert sys.version_info[:2] == (3, 12)
before = verify_files()
sys.path.insert(0, str(ROOT))
# The source has been inspected: importing verify does not call main or Django.
os.environ.pop('BOS_TEST_DEPENDENCIES', None)
from scripts import verify
assert type(verify.ROOT).__name__ == 'WindowsPath'
assert Path(verify.__file__).resolve() == (ROOT / 'scripts/verify.py').resolve()
actual_digest = verify.source_digest()
assert actual_digest == EXPECTED, actual_digest

stream = io.StringIO()
suite = unittest.defaultTestLoader.loadTestsFromName('scripts.test_source_digest')
unit = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
assert unit.testsRun == 2 and unit.wasSuccessful() and not unit.skipped
(OUT / 'unit.log').write_text(stream.getvalue(), encoding='utf-8')

probes = []
# Default inherited workspace permissions; retain fixtures as audit evidence.
# tempfile on this Windows sandbox created a private ACL inaccessible to its runner.
probe_path = BASE / ('native-source-probe-' + uuid.uuid4().hex[:12])
probe_path.mkdir()
with nullcontext(probe_path) as temporary:
    native = Path(temporary)
    original_entries = [
        ('START_DEMO.bat', b'@echo off\n'),
        ('assets/Logo.png', b'\x89PNG\r\n'),
        ('operations/seed/documents/D01.md', b'# Document\n'),
        ('operations/seed/documents.json', b'[]\n'),
        ('scripts/Z.py', b'z = 1\n'),
        ('scripts/_helper.py', b'helper = 1\n'),
        ('scripts/a.py', b'a = 1\n'),
    ]
    for name, data in reversed(original_entries):
        file = native / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    expected = known_digest(original_entries)
    with patch.object(verify, 'ROOT', native):
        assert verify.source_digest() == expected
        probes.append('native_mixed_case_and_directory_prefix_known_order')
        (native / 'scripts/a.py').write_bytes(b'a = 1\r\n')
        assert verify.source_digest() == expected
        probes.append('text_crlf_normalized')
        (native / 'assets/Logo.png').write_bytes(b'\x89PNG\n')
        assert verify.source_digest() != expected
        probes.append('binary_crlf_change_detected')
        (native / 'assets/Logo.png').write_bytes(b'\x89PNG\r\n')
        (native / 'scripts/a.py').write_bytes(b'a = 2\n')
        assert verify.source_digest() != expected
        probes.append('content_mutation_detected')
        (native / 'scripts/a.py').write_bytes(b'a = 1\n')
        (native / 'scripts/a.py').rename(native / 'scripts/b.py')
        assert verify.source_digest() != expected
        probes.append('path_mutation_detected')
        (native / 'scripts/b.py').rename(native / 'scripts/a.py')
        (native / 'scripts/__pycache__').mkdir()
        (native / 'scripts/__pycache__/ignored.pyc').write_bytes(b'ignored')
        assert verify.source_digest() == expected
        probes.append('bytecode_excluded')
after = verify_files()
assert before == after
report = {
    'schema': 'bos.native-windows-source.v1', 'card': 'PLAN-SOURCE-WINDOWS',
    'status': 'PASS_SCOPED_NATIVE_WINDOWS_SOURCE', 'candidate_commit': HEAD,
    'comparison_linux_ci_commit': '8060075455206257d6283c70906facca98f0bc1a',
    'comparison_linux_ci_run': 35507888776,
    'expected_source_sha256': EXPECTED, 'actual_source_sha256': actual_digest,
    'runtime_files_verified_before_and_after': len(before), 'runtime_bytes': sum(x['size'] for x in before),
    'runtime_unchanged': before == after, 'casefold_path_and_directory_collisions': 0,
    'whole_git_tree_verified': False, 'snapshot_scope': 'Exact runtime digest inputs plus AGENTS.md; no Git history or other docs reconstructed',
    'environment': {'system': platform.system(), 'os_name': os.name, 'platform': platform.platform(),
                    'python': sys.version, 'python_executable': sys.executable, 'path_type': type(verify.ROOT).__name__},
    'existing_unit_methods': unit.testsRun, 'unit_skipped': len(unit.skipped), 'native_file_probes': probes,
    'elapsed_seconds': round(time.monotonic() - started, 3), 'exit_code': 0,
    'application_or_database_started': False, 'full_suite_run': False, 'gate11_accepted': False,
    'technical_ready': False, 'pilot_allowed': False,
}
(OUT / 'runtime-manifest.json').write_text(json.dumps(before, indent=2) + '\n', encoding='utf-8')
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
