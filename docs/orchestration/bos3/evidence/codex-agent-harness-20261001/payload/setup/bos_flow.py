"""Bounded BOS coordination commands; no model for indexing, no automatic claims."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('D:/3/BOSDev')
HOME_DIR = Path('C:/Users/user/AppData/Local/BOSDev')
sys.path.insert(0, str(HOME_DIR / 'tools'))
sys.path.insert(0, str(ROOT / 'setup'))
from bos_dev import atomic_json, read_json, state_lock
import codex_channel as channel
import local_flow

ACTORS = ('main', 'integrator', 'writer', 'design', 'quality', 'enablement')
CURSORS = dict(zip(ACTORS, ('main_cursor', 'integrator_cursor', 'canonical_writer_cursor', 'design_cursor', 'quality_cursor', 'enablement_cursor')))
STAGES = ('assignment', 'report', 'review', 'package', 'decision', 'blocked')


class FlowError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise FlowError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unwrap(result):
    if 'structuredContent' in result:
        return result['structuredContent']
    if 'polls' in result:
        return result
    for block in result.get('content', []):
        if block.get('type') == 'text':
            try:
                value = json.loads(block['text'])
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    raise FlowError('Control response has no structured status')


def valid_poll(poll, expected_ids):
    if not isinstance(poll, dict) or poll.get('error') is not None:
        return False
    thread = poll.get('thread')
    if (not isinstance(thread, dict) or thread.get('id') not in expected_ids
            or thread.get('hostId') != 'local' or thread.get('error') is not None):
        return False
    status = thread.get('status')
    turn = poll.get('latestTurn')
    return (isinstance(status, dict) and status.get('type') in ('active', 'idle', 'notLoaded')
            and status.get('error') is None
            and (turn is None or (isinstance(turn, dict) and turn.get('error') is None
                                 and turn.get('status') in ('completed', 'inProgress'))))


def accepted_status(status):
    # Explicit accepted families present in the assigned canonical queue.
    # Partial DESIGN_BRIEF_ACCEPTED_*_ACTIVE and INCOMPLETE_* are not completion.
    value = str(status).upper()
    return (value in ('DONE', 'COMPLETED', 'ACCEPTED')
            or value == 'ACCEPT_SCOPED' or value.startswith('ACCEPT_SCOPED_')
            or value == 'ACCEPTED_SCOPED' or value.startswith('ACCEPTED_SCOPED_')
            or value == 'PUBLISHED_ACCEPT_SCOPED' or value.startswith('PUBLISHED_ACCEPT_SCOPED_'))


def refresh(home=HOME_DIR, root=ROOT, client_factory=channel.AppTools):
    """One batch plus one request for each absent actor. Never wakes a thread."""
    with state_lock(home):
        checkpoint = read_json(home / 'observer.json')
    targets = []
    for alias in ACTORS:
        target = {'threadId': channel.TARGETS[alias], 'hostId': 'local'}
        if checkpoint.get(CURSORS[alias]):
            target['afterCursor'] = checkpoint[CURSORS[alias]]
        targets.append(target)
    seen, errors = {}, []
    with client_factory() as client:
        def read(targets_to_read):
            try:
                response = unwrap(client.call('wait_threads', {'targets': targets_to_read, 'timeoutMs': 0}))
                response_errors = response.get('errors') or []
                expected = {t['threadId'] for t in targets_to_read}
                for poll in response.get('polls', []):
                    if not response_errors and valid_poll(poll, expected):
                        seen[poll['thread']['id']] = poll
                    else:
                        errors.append({'reason': 'invalid_or_error_poll', 'expected_thread_ids': sorted(expected)})
                errors.extend(response_errors)
            except (channel.ChannelError, FlowError, OSError, ValueError) as exc:
                errors.append({'reason': type(exc).__name__, 'message': str(exc)[:300]})
        read(targets)
        for target in targets:
            if target['threadId'] not in seen:
                # The cursor may suppress an unchanged actor in the batch.
                # One fresh fallback must request its current snapshot.
                read([{'threadId': target['threadId'], 'hostId': target['hostId']}])
    checked = now()
    evidence = root / 'reports' / 'flow' / 'LATEST_STATUS.json'
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with state_lock(home):
        observer = read_json(home / 'observer.json')
        control = observer.setdefault('control_channel', {})
        for alias in ACTORS:
            snapshot = control.setdefault(alias + '_snapshot', {})
            poll = seen.get(channel.TARGETS[alias])
            if poll is None:
                snapshot['last_known_status'] = snapshot.get('status')
                snapshot['status'] = 'unknown'
                snapshot['status_attempted_at_utc'] = checked
                snapshot['fresh_status_error'] = 'Actor absent from bounded refresh; previous result retained'
                continue
            turn = poll.get('latestTurn') or {}
            snapshot.update(thread_id=channel.TARGETS[alias], status=poll['thread']['status']['type'],
                            turn=turn.get('id'), turn_status=turn.get('status'), cursor=poll.get('cursor'),
                            checked_at_utc=checked, evidence=str(evidence), fresh_status_error=None,
                            turn_error=turn.get('error'), status_attempted_at_utc=None)
            # Status is distinct from progress: do not replace assignment/results from chat text.
            if poll.get('cursor'):
                observer[CURSORS[alias]] = poll['cursor']
        control['last_checked_at'] = checked
        observer['last_observed_at'] = checked
        atomic_json(evidence, {'schema': 'bos.flow-status.v1', 'checked_at_utc': checked,
                              'polls': list(seen.values()), 'errors': errors,
                              'missing_actors': [a for a in ACTORS if channel.TARGETS[a] not in seen]})
        atomic_json(home / 'observer.json', observer)
    board = local_flow.collect(home, root)
    output = root / 'reports' / 'local_flow'
    output.mkdir(parents=True, exist_ok=True)
    local_flow.atomic_text(output / 'CURRENT.json', json.dumps(board, ensure_ascii=False, indent=2) + '\n')
    local_flow.atomic_text(output / 'CURRENT_RU.md', local_flow.markdown(board))
    return board


def compact(board, policy):
    generated = board.get('generated_at_utc')
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(generated)).total_seconds()
    except (TypeError, ValueError):
        age = None
    identities = board.get('identities', {})
    candidate = identities.get('working_candidate')
    candidate_keys = ('status', 'commit', 'source_commit', 'source_sha256',
                      'base_commit', 'candidate_version')
    current_candidate = ({key: candidate[key] for key in candidate_keys
                          if key in candidate and isinstance(candidate[key], (str, int, float, bool, type(None)))}
                         if isinstance(candidate, dict) else None)
    source = {key: identities.get(key) for key in
              ('published_commit', 'local_canonical_commit', 'last_accepted_runtime_commit')}
    sync_source = identities.get('sync_source')
    source['sync_source'] = ({key: sync_source.get(key) for key in ('path', 'commit')}
                             if isinstance(sync_source, dict) else None)
    source['working_candidate'] = current_candidate
    source['working_candidate_details_in'] = 'CURRENT.json'
    source['runtime_scope'] = 'historical_accepted_runtime_pin'
    source['working_candidate_scope'] = 'historical_working_candidate_pin'
    source['sync_source_scope'] = 'historical_lab_sync_pin'
    source['documentation_publication'] = board.get('source_scope', {}).get('documentation_publication')
    source['accepted_package'] = board.get('source_scope', {}).get('accepted_package')
    return {'generated_at_utc': generated, 'index_age_seconds': None if age is None else round(age),
            'refresh_needed': age is None or age > policy['snapshot_max_age_seconds'],
            'actors': board.get('actors', {}),
            'source': source,
            'new_reports': len(board.get('new_or_changed_reports', [])),
            'pending_author_review': len(board.get('ready_for_review_author_reports', [])),
            'incomplete_report_schemas': len(board.get('incomplete_report_schemas', [])),
            'read_errors': board.get('read_errors', []),
            'parallel_limit': {'per_root_subtasks': 3, 'including_root': 4,
                               'free_subagent_slots': 'query collaboration.list_agents in owning root'},
            'automatic_product_claims': False, 'model_calls_by_command': 0}


def next_steps(board, policy):
    overview = compact(board, policy)
    actions = []
    if overview['refresh_needed'] or overview['read_errors']:
        actions.append({'kind': 'refresh_or_repair_index', 'owner': 'observer',
                        'ready_to_execute_product_work': False})
    for report in board.get('new_or_changed_reports', [])[:policy['max_report_references']]:
        actions.append({'kind': 'reconcile_exact_report_hash', 'owner': 'observer',
                        'path': report['path'], 'sha256': report['sha256'],
                        'author_status': report.get('author_status'), 'model_profile': 'none',
                        'note': 'Hash/schema checks are mechanical; acceptance requires actual independent evidence'})
    for report in board.get('ready_for_review_author_reports', [])[:policy['max_report_references']]:
        actions.append({'kind': 'check_existing_review_assignment', 'proposed_owner': 'quality',
                        'path': report['path'], 'sha256': report['sha256'], 'model_profile': 'review',
                        'prerequisite': 'Current integrator checks exact source, independence, current owner and free slot against canonical BoS 3.0 plan'})
    def available(alias, actor):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(actor['checked_at_utc'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            return False
        return (not overview['refresh_needed'] and not overview['read_errors']
                and -60 <= age <= policy['snapshot_max_age_seconds']
                and actor.get('thread_id') == channel.TARGETS.get(alias)
                and actor.get('fresh_status_error') is None and actor.get('turn_error') is None
                and actor.get('status') == 'idle' and actor.get('turn_status') == 'completed')
    idle = [a for a, s in board.get('actors', {}).items()
            if a not in ('main', 'integrator') and available(a, s)]
    return {'overview': overview, 'actions': actions, 'available_chat_owners': idle,
            'action_source': 'legacy C control-home index; advisory for BoS 3.0',
            'product_assignment_authority': False,
            'product_decision_source': 'docs/orchestration/bos3/CONTROL_STATE.json and ACTIVE_WORK_PLAN_RU.md',
            'idle_policy': 'No model call until a new authorized task or actionable event exists',
            'parallel_conditions': ['Independent completed dependencies', 'Exact assigned source and separate copy',
                                    'Non-overlapping allowlists and current ownership', 'A free actual subagent slot',
                                    'ERP mutex remains serial; integrations remain serial'],
            'dispatch_performed': False, 'claims_performed': False}


def verify_reference(ref, policy):
    require(isinstance(ref, dict) and isinstance(ref.get('path'), str), 'Reference requires path')
    path = Path(ref['path']).resolve()
    roots = [Path(p).resolve() for p in policy['evidence_roots']]
    require(any(path.is_relative_to(root) for root in roots), 'Reference outside designated BOS roots')
    require(path.is_file(), 'Missing reference: ' + str(path))
    require(re.fullmatch('[0-9a-f]{64}', ref.get('sha256', '')) is not None, 'Reference needs exact SHA256')
    require(digest(path) == ref['sha256'], 'Reference changed: ' + str(path))
    return path


def prepare_handoff(packet, policy, origin, home=HOME_DIR):
    require(packet.get('schema') == 'bos.flow-handoff.v1', 'Wrong handoff schema')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', packet.get('message_id', '')) is not None, 'Invalid message ID')
    require(origin in channel.TARGETS.values(), 'Caller must be a designated BOS chat')
    target, kind, stage = packet.get('target'), packet.get('kind'), packet.get('stage')
    require(target in channel.TARGETS and channel.TARGETS[target] != origin, 'Unknown or self target')
    require(kind in ('assignment', 'report', 'coordination') and stage in STAGES, 'Invalid kind/stage')
    require(isinstance(packet.get('card_id'), str) and bool(packet['card_id'].strip()), 'Missing existing card/handoff ID')
    require(isinstance(packet.get('summary'), str) and 0 < len(packet['summary']) <= policy['max_summary_chars'], 'Summary length out of bounds')
    source = packet.get('source') or {}
    require(isinstance(source, dict), 'Source must be an object')
    require(bool(re.fullmatch('[0-9a-f]{40}', str(source.get('commit', '')))) or
            bool(re.fullmatch('[0-9a-f]{64}', str(source.get('sha256', '')))), 'Exact source commit or source SHA256 required')
    refs = packet.get('references')
    require(isinstance(refs, list) and 1 <= len(refs) <= policy['max_report_references'], 'Bounded evidence references required')
    for ref in refs:
        verify_reference(ref, policy)
    assignment_refs = []
    if kind == 'assignment':
        require(stage == 'assignment' and origin == channel.TARGETS['main'], 'Only main may allocate product work')
        require(target in ('writer', 'design', 'quality'), 'Assignment target must be a worker')
        require(isinstance(packet.get('allowlist'), list) and packet['allowlist'], 'Assignment requires exact allowlist')
        require(isinstance(packet.get('dependencies'), list), 'Assignment dependencies must be explicit')
        require(bool(packet.get('worktree')) and bool(packet.get('done_when')), 'Assignment needs copy and DoD')
        queue_path = verify_reference(packet.get('canonical_queue_ref'), policy)
        assignment_refs.append(('Canonical queue', packet['canonical_queue_ref']))
        queue = read_json(queue_path)
        tasks = queue.get('tasks', [])
        tasks = list(tasks.values()) if isinstance(tasks, dict) else tasks
        by_id = {t.get('id'): t for t in tasks}
        require(packet['card_id'] in by_id, 'Card is absent from referenced canonical queue')
        card = by_id[packet['card_id']]
        require(not accepted_status(card.get('status')), 'Accepted canonical card must not be assigned again')
        canonical_dependencies = card.get('depends_on', [])
        require(isinstance(canonical_dependencies, list), 'Canonical dependencies malformed')
        require(set(packet['dependencies']) == set(canonical_dependencies), 'Dependencies must match canonical card')
        require(all(dep in by_id and accepted_status(by_id[dep].get('status')) for dep in canonical_dependencies),
                'Canonical dependencies are not completed')
        config = read_json(home / 'config.json')
        broad = any(x.get('status') in ('in_progress', 'review', 'blocked') and '.' in x.get('allowlist', [])
                    for x in config.get('external_owners', []))
        if broad:
            verify_reference(packet.get('ownership_handoff_ref'), policy)
        if packet.get('ownership_handoff_ref'):
            verify_reference(packet['ownership_handoff_ref'], policy)
            assignment_refs.append(('Explicit ownership handoff', packet['ownership_handoff_ref']))
    else:
        require(stage != 'assignment', 'Reports and coordination cannot allocate work')
        if kind == 'coordination':
            require(target in ('main', 'integrator', 'observer'), 'Coordination goes to a coordinator or observer')
    if stage in ('decision', 'package'):
        require(target in ('main', 'integrator'), 'Package/decision must reach a coordinator; no automatic apply')
    profile_name = packet.get('profile', 'standard' if kind == 'assignment' else 'inherit')
    require(profile_name in policy['profiles'], 'Unknown model profile')
    require(profile_name != 'none', 'No-model profile cannot send a model task')
    if target in ('main', 'integrator'):
        require(profile_name == 'inherit', 'Keep coordinator model; offload small work to a worker')
    if profile_name == 'economy':
        require(packet.get('task_class') in ('evidence_index', 'summary', 'mechanical_docs'), 'Economy is limited to small mechanical work')
        require(stage not in ('review', 'decision'), 'Independent verdict or approval cannot use economy profile')
    if packet.get('task_class') == 'independent_review':
        require(profile_name in ('review', 'critical'), 'Independent review needs an explicit review or critical profile')
    lines = ['БОС: передача по цепочке', f"Карточка: {packet['card_id']}; этап: {stage}; тип: {kind}.",
             f"Источник: {json.dumps(source, ensure_ascii=False, sort_keys=True)}", packet['summary'], '', 'Точные материалы:']
    lines += [f"- {r['path']} | SHA256 {r['sha256']}" for r in refs]
    if kind == 'assignment':
        distinct_refs = {(r['path'], r['sha256']) for r in refs}
        distinct_refs.update((r['path'], r['sha256']) for _, r in assignment_refs)
        require(len(distinct_refs) <= policy['max_report_references'], 'Assignment reference count exceeds context cap')
        lines += ['', 'Основания назначения:']
        lines += [f"- {label}: {r['path']} | SHA256 {r['sha256']}" for label, r in assignment_refs]
        lines += ['', 'Назначение главного:', 'Копия: ' + str(packet['worktree']),
                  'Allowlist: ' + json.dumps(packet['allowlist'], ensure_ascii=False),
                  'Зависимости: ' + json.dumps(packet['dependencies'], ensure_ascii=False),
                  'Готово когда: ' + str(packet['done_when']),
                  'Перед product claim проверить каноническую карточку/зависимости/владение, выполнить разрешённый sync; эта доставка claim не создаёт.']
    lines += ['', 'Сохранять исходное авторство; передать следующий содержательный результат назначенному получателю через ledger.',
              'Доставка не является приёмкой. Не отвечать квитанцией и не повторять успешные проверки без новой причины.',
              ('Legacy main рассматривает только старый assignment; ' if kind == 'assignment' else
                'Текущий integrator рассматривает и применяет пакеты последовательно; ') +
               'ERP mutex и действующие P05/A09/A10/A11 сохраняются.']
    text = '\n'.join(lines) + '\n'
    require(len(text) <= policy['max_message_chars'], 'Handoff exceeds context cap; use short file references')
    return text, policy['profiles'][profile_name]


def handoff(packet_path, policy, execute=False, home=HOME_DIR, root=ROOT):
    packet = read_json(packet_path)
    text, profile = prepare_handoff(packet, policy, os.environ.get('CODEX_THREAD_ID'), home)
    result = {'message_id': packet['message_id'], 'target': packet['target'],
              'profile': packet.get('profile', 'standard' if packet['kind'] == 'assignment' else 'inherit'),
              'message_chars': len(text), 'state': 'VALIDATED_NOT_SENT', 'source_packet_sha256': digest(packet_path)}
    if not execute:
        return result
    out = root / 'handoffs' / 'flow_messages'
    out.mkdir(parents=True, exist_ok=True)
    message = out / (packet['message_id'] + '.md')
    with state_lock(home):
        if message.exists():
            require(message.read_text(encoding='utf-8') == text, 'Stable ID already has different prepared content')
        else:
            local_flow.atomic_text(message, text)
    command = [sys.executable, '-B', str(home / 'tools/codex_channel.py'), 'send', '--target', packet['target'],
               '--message-file', str(message), '--message-id', packet['message_id']]
    if profile.get('model'):
        command += ['--model', profile['model'], '--thinking', profile['thinking']]
    completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=60)
    require(completed.returncode == 0, 'Ledger delivery refused or uncertain; inspect existing ID, do not resend: ' + completed.stderr[-500:])
    delivery = json.loads(completed.stdout)
    result.update(state=delivery.get('delivery', {}).get('status'), delivery=delivery,
                  requested_model=profile.get('model'), requested_thinking=profile.get('thinking'),
                  actual_model_verified=False, model_note='Requested via supported transport; runtime model not inferred from request')
    receipt = root / 'reports' / 'flow' / (packet['message_id'] + '.json')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with state_lock(home):
        atomic_json(receipt, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'refresh', 'next', 'models', 'handoff'))
    parser.add_argument('--packet', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--policy', type=Path, default=ROOT / 'plans/FLOW_POLICY.json')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        policy = read_json(args.policy)
        if args.action == 'models':
            result = {'profiles': policy['profiles'], 'idle': 'no model call', 'global_model_changed': False}
        elif args.action == 'handoff':
            require(args.packet is not None, '--packet is required')
            result = handoff(args.packet, policy, args.execute)
        else:
            board = refresh() if args.action == 'refresh' else read_json(ROOT / 'reports/local_flow/CURRENT.json')
            if args.action == 'next':
                result = next_steps(board, policy)
                from bos3_guidance import current_bos3
                result['current_bos3'] = current_bos3()
            else:
                result = compact(board, policy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FlowError, channel.ChannelError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('BOS flow: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
