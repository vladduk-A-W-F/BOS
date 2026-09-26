"""Opt-in stdlib process proof in an explicit owned root; no Django, browser, DB, or TCP."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from review_process import Lifecycle, Windows, atomic_json, child_gate, read_json


def lifecycle(root):
    return Lifecycle(root, [sys.executable, '-B', str(Path(__file__).resolve()), 'child', '--root', str(root)],
                     getattr(sys, '_base_executable', sys.executable))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['proof', 'start', 'stop', 'child'])
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not args.root.is_absolute():
        parser.error('An explicit absolute owned proof root is required')
    if args.action == 'child':
        proof = child_gate(root)
        atomic_json(root / 'child-active.json', {'child': proof['child'], 'stdlib_only': True})
        time.sleep(120)
        return
    if args.action == 'start':
        def ready(alive):
            deadline = time.monotonic() + 10
            while not (root / 'child-active.json').exists():
                alive()
                if time.monotonic() >= deadline:
                    raise RuntimeError('Proof child never passed ownership gate')
                time.sleep(.05)
        with (root / 'child.log').open('a', encoding='utf-8') as log:
            state = lifecycle(root).start(environment=dict(os.environ), cwd=root, log=log, readiness=ready)
        atomic_json(root / 'start-returned.json', {'stage': state['stage'], 'controller_pid': os.getpid()})
        return
    if args.action == 'stop':
        atomic_json(root / 'stop-receipt.json', lifecycle(root).stop())
        return
    if root.exists():
        raise RuntimeError('Proof root must be new; refusing to reuse any runtime.')
    root.mkdir(parents=True)
    for directory in ('data', 'media'):
        (root / directory).mkdir()
        (root / directory / 'sentinel.txt').write_text('synthetic proof sentinel', encoding='utf-8')
    receipt = {'scope': 'stdlib-only Windows lifecycle proof; no BoS/browser/DB/TCP', 'passed': False}
    try:
        base = [sys.executable, '-B', str(Path(__file__).resolve())]
        started = subprocess.run([*base, 'start', '--root', str(root)], capture_output=True, text=True,
                                 timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        (root / 'start-raw.log').write_text(started.stdout + started.stderr, encoding='utf-8')
        if started.returncode:
            raise RuntimeError('Proof controller start failed; inspect start-raw.log')
        state = read_json(root / 'process.json')
        status = lifecycle(root).status()
        if not status.get('child_running') or not status.get('launcher_running'):
            raise RuntimeError('Persistent child did not survive successful controller exit')
        receipt['persistent_after_controller_exit'] = True
        receipt['child'] = state['child']
        receipt['launcher'] = state['launcher']
        stopped = subprocess.run([*base, 'stop', '--root', str(root)], capture_output=True, text=True,
                                 timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        (root / 'stop-raw.log').write_text(stopped.stdout + stopped.stderr, encoding='utf-8')
        if stopped.returncode:
            raise RuntimeError('Proof controller stop failed; inspect stop-raw.log')
        stop = read_json(root / 'stop-receipt.json')
        receipt.update(child_exit_verified=stop['child_exit_verified'],
                       launcher_exit_verified=stop['launcher_exit_verified'])
        receipt['sentinels_retained'] = all((root / name / 'sentinel.txt').read_text(encoding='utf-8')
                                          == 'synthetic proof sentinel' for name in ('data', 'media'))
        receipt['process_record_removed'] = not (root / 'process.json').exists()
        receipt['passed'] = all(receipt[key] for key in ('persistent_after_controller_exit', 'child_exit_verified',
                                                       'launcher_exit_verified', 'sentinels_retained', 'process_record_removed'))
    finally:
        if (root / 'process.json').exists():
            try:
                receipt['failure_cleanup'] = lifecycle(root).stop()
            except BaseException as error:
                receipt['cleanup_pending'] = type(error).__name__
        atomic_json(root / 'receipt.json', receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
