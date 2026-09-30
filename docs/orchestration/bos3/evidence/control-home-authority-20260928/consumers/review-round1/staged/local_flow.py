"""Read-only BOS flow index. Writes only requested reports, never claims or sends."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

DEFAULT_HOME = Path('D:/3/BOSDev/control-home')
DEFAULT_ROOT = Path('D:/3/BOSDev')
TOOLS = DEFAULT_HOME / 'tools'
sys.path.insert(0, str(TOOLS))
from bos_dev import resolve_control_home, state_lock
REQUIRED = ('report_id', 'owner', 'card_id', 'source_commit', 'executor_available')
PENDING_REVIEW = frozenset({
    'READY_FOR_REVIEW', 'READY_FOR_INDEPENDENT_REVIEW',
    'PREPARATION_READY_FOR_INDEPENDENT_REVIEW',
    'PRIVATE_PATCH_READY_FOR_INDEPENDENT_REVIEW',
    'PRIVATE_PLAN_READY_FOR_ROOT_REVIEW', 'READY_FOR_REVIEW_PARTIAL_VALIDATION',
    'READY_FOR_INDEPENDENT_CODE_REVIEW_NOT_RUN',
    'READY_FOR_INDEPENDENT_SOURCE_REVIEW_NOT_RUN',
    'PASS_SCOPED_PENDING_INDEPENDENT_RESULT_REVIEW',
    'SOURCE_FROZEN_FOR_INDEPENDENT_REVIEW',
    'TARGETED_VALIDATION_COMPLETE_PENDING_WHOLE_CANDIDATE_REVIEW',
    'VALIDATION_COMPLETE_PENDING_REVIEW_AND_DESIGN_PATCH',
})


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def git_read(executable, path, *args):
    result = subprocess.run([str(executable), '--no-optional-locks', '-C', str(path), *args],
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=20)
    if result.returncode:
        raise RuntimeError('Git read failed: ' + ' '.join(args[:2]))
    return result.stdout


def repo_state(executable, path):
    result = {'path': str(path), 'head': None, 'dirty': None, 'error': None}
    try:
        result['head'] = git_read(executable, path, 'rev-parse', 'HEAD').strip()
        result['branch'] = git_read(executable, path, 'branch', '--show-current').strip()
        result['dirty'] = bool(git_read(executable, path, 'status', '--porcelain', '-z'))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result['error'] = str(exc)
    return result


def index_report(path, raw, known_by_hash):
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('template_only') is True:
        return None
    if data.get('schema') != 'bos.department-report.v1':
        return None
    digest = hashlib.sha256(raw).hexdigest()
    known = known_by_hash.get(digest, {})
    missing = [key for key in REQUIRED if key not in data]
    disposition = known.get('current_disposition')
    return {
        'path': str(path), 'sha256': digest,
        'report_id': data.get('report_id'),
        'compatibility_id': data.get('report_id') or 'file:' + str(path),
        'owner': data.get('owner') or data.get('author'),
        'author_thread_id': data.get('author_thread_id'),
        'card_id': data.get('card_id'),
        'source_commit': data.get('source_commit') or data.get('commit'),
        'source_sha256': data.get('source_sha256'),
        'reported_at_utc': data.get('reported_at_utc'),
        'author_status': data.get('status'),
        'executor_available_reported': data.get('executor_available'),
        'schema_missing': missing,
        'indexed_before_with_exact_hash': bool(known),
        'current_disposition': disposition,
        'resolution_evidence': known.get('resolution_evidence'),
        'needs_controller_reconciliation': not bool(known),
        'author_status_is_acceptance': False,
    }


def ready_reports(reports):
    """Only unresolved author preparation; this never grants acceptance or work."""
    return [r for r in reports
            if not r['current_disposition']
            and (r['author_status'] or '').upper() in PENDING_REVIEW]


def sync_source_problem(source, pin):
    if not source or source.get('error') or not source.get('head') or source.get('dirty') is None:
        return 'sync_source_unknown'
    if source['head'] != pin or source['dirty']:
        return 'sync_source_drift_or_dirty'
    return None


def collect(home, root):
    # The shared queue/config are read together. Git and file scans do not hold it.
    home = resolve_control_home(home)
    with state_lock(home):
        config = load(home / 'config.json')
        queue = load(home / 'queue.json')
        observer = load(home / 'observer.json')
    executable = config.get('git_executable')
    sync = config.get('sync_source') or {}
    # Explicitly keep committed source, published source and working digest apart.
    identities = {
        'published_commit': observer.get('published_head') or observer.get('source_commit'),
        'local_canonical_commit': observer.get('local_canonical_commit'),
        'last_accepted_runtime_commit': observer.get('runtime_commit'),
        'working_candidate': observer.get('working_candidate_current'),
        'sync_source': {key: sync.get(key) for key in
                        ('path', 'commit', 'approved_by_thread_id', 'approval_message_id')},
    }
    source = repo_state(executable, sync['path']) if sync.get('path') else None
    tasks = queue.get('tasks', {})
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    active = [t for t in tasks if t.get('status') in ('in_progress', 'review', 'blocked')]
    broad = [x.get('id') for x in config.get('external_owners', [])
             if x.get('status') in ('in_progress', 'review', 'blocked')
             and '.' in x.get('allowlist', [])]
    lanes = []
    for name, entry in config.get('lanes', {}).items():
        lane = repo_state(executable, entry['worktree'])
        lane.update({'lane': name, 'claims': [t.get('id') for t in active if t.get('lane') == name],
                     'behind_source': None, 'ahead_source': None,
                     'broad_external_owners': broad, 'reasons': [],
                     'product_claim_authorized': False})
        if lane['error']:
            lane['reasons'].append('git_read_unavailable')
        if lane['dirty']:
            lane['reasons'].append('dirty_worktree')
        if lane['claims']:
            lane['reasons'].append('active_claim')
        if not sync.get('commit') or not source:
            lane['reasons'].append('sync_source_not_assigned')
        elif sync_source_problem(source, sync['commit']):
            lane['reasons'].append(sync_source_problem(source, sync['commit']))
        elif lane['head']:
            try:
                counts = git_read(executable, source['path'], 'rev-list', '--left-right',
                                  '--count', lane['head'] + '...' + sync['commit']).split()
                lane['ahead_source'], lane['behind_source'] = map(int, counts)
                if lane['ahead_source']:
                    lane['reasons'].append('not_fast_forward')
                elif lane['behind_source']:
                    lane['reasons'].append('needs_sync')
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                lane['reasons'].append('ancestry_unknown')
        if broad:
            lane['reasons'].append('external_owner_whole_repo')
        lane['availability'] = 'requires_assignment' if not lane['reasons'] else 'limited'
        lanes.append(lane)
    known = {r['sha256']: r for r in observer.get('reporting', {}).get('reports', [])
             if r.get('sha256')}
    reports, errors = [], []
    for path in sorted((root / 'reports').rglob('*.json')):
        if 'local_flow' in path.relative_to(root / 'reports').parts:
            continue
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                errors.append({'path': str(path), 'reason': 'report_larger_than_4MiB'})
                continue
            item = index_report(path, path.read_bytes(), known)
            if item:
                reports.append(item)
        except (OSError, ValueError, TypeError) as exc:
            errors.append({'path': str(path), 'reason': type(exc).__name__})
    snapshots = observer.get('control_channel', {})
    actors = {role: {k: snapshots.get(role + '_snapshot', {}).get(k) for k in
                    ('thread_id', 'status', 'turn_status', 'assignment',
                     'last_confirmed_result_at', 'result_evidence', 'blocker',
                     'checked_at_utc', 'fresh_status_error', 'turn_error')}
              for role in ('main', 'writer', 'design', 'quality')}
    cards = observer.get('active_cards_current', [])
    return {'schema': 'bos.local-flow.v1', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'observer_observed_at': observer.get('last_observed_at'),
            'mode': 'READ_ONLY_INDEX_NO_AUTO_DISPATCH', 'identities': identities,
            'sync_source_live': source, 'lanes': lanes, 'actors': actors,
            'current_cards': cards, 'current_cards_source': 'observer.active_cards_current',
            'author_reports': reports, 'ready_for_review_author_reports': ready_reports(reports),
            'new_or_changed_reports': [r for r in reports if r['needs_controller_reconciliation']],
            'incomplete_report_schemas': [r for r in reports if r['schema_missing']],
            'read_errors': errors, 'does_not_claim_product_readiness': True}


def markdown(board):
    def cell(value):
        return str(value if value is not None else 'неизвестно').replace('|', '\\|').replace('\n', ' ')
    lines = ['# БОС — локальный поток', '',
             'Обновлено: ' + board['generated_at_utc'],
             'Это индекс фактов и передачи работ; новые задачи и приёмка автоматически не создаются.', '',
             '## Версии', '', '| Вид | Значение |', '|---|---|']
    for k, v in board['identities'].items():
        lines.append('| ' + k + ' | ' + cell(v) + ' |')
    lines += ['', '## Исполнители', '', '| Роль | Статус | Текущее назначение |', '|---|---|---|']
    for role, s in board['actors'].items():
        lines.append(f"| {role} | {cell(s['status'])}/{cell(s['turn_status'])} | {cell(s['assignment'])} |")
    lines += ['', '## Лабораторные копии', '', '| Lane | HEAD | Отставание | Условия следующего старта |', '|---|---|---|---|']
    for lane in board['lanes']:
        lines.append(f"| {lane['lane']} | {cell(lane['head'])} | {cell(lane['behind_source'])} | {cell(', '.join(lane['reasons']) or 'Нужна назначенная карточка')} |")
    lines += ['', '## Новые или изменённые авторские отчёты', '']
    for r in board['new_or_changed_reports']:
        lines.append(f"- [{cell(r['compatibility_id'])}]({Path(r['path']).as_posix()}): {cell(r['author_status'])}; SHA256 `{r['sha256']}`.")
    if not board['new_or_changed_reports']:
        lines.append('Новых файлов относительно проверенного индекса контролёра нет.')
    lines += ['', '## Ожидающая авторская подготовка', '', 'Список показывает авторскую готовность; независимая приёмка указана отдельно в evidence.', '']
    for r in board['ready_for_review_author_reports']:
        lines.append(f"- [{cell(r['compatibility_id'])}]({Path(r['path']).as_posix()}): {cell(r['author_status'])}.")
    lines += ['', '## Полнота схемы отчётов', '']
    for r in board['incomplete_report_schemas']:
        lines.append(f"- [{Path(r['path']).name}]({Path(r['path']).as_posix()}): отсутствуют {', '.join(r['schema_missing'])}; исходный отчёт сохранён.")
    if board['read_errors']:
        lines += ['', 'Ошибки чтения: ' + cell(board['read_errors'])]
    return '\n'.join(lines) + '\n'


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    board = collect(args.home, args.root)
    if args.output_dir:
        # Restrict the optional mutation to this flow's report directory.
        allowed = (args.root / 'reports' / 'local_flow').resolve()
        if args.output_dir.resolve() != allowed:
            raise SystemExit('output-dir must be ROOT/reports/local_flow')
        atomic_text(allowed / 'CURRENT.json', json.dumps(board, ensure_ascii=False, indent=2) + '\n')
        atomic_text(allowed / 'CURRENT_RU.md', markdown(board))
    print(json.dumps({'schema': board['schema'], 'read_errors': board['read_errors'],
                      'lanes': board['lanes'], 'new_reports': len(board['new_or_changed_reports']),
                      'pending_author_reports': len(board['ready_for_review_author_reports']),
                      'incomplete_report_schemas': len(board['incomplete_report_schemas']),
                      'output_dir': str(args.output_dir) if args.output_dir else None}, ensure_ascii=False))
    return 1 if board['read_errors'] else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
