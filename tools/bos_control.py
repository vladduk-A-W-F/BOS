"""Read-only BoS setup inspector. Does not start Django, agents, CI or APIs."""
import argparse
import ast
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'orchestration'
BOS3_DOCS = DOCS / 'bos3'

ACTIVE_CARD_MARKERS = ('READY', 'ACTIVE', 'IN_PROGRESS')
BLOCKED_PRIORITY_STATUSES = {'BLOCKED', 'PARTIAL', 'DEFERRED', 'READY', 'IN_PROGRESS', 'DONE'}
PENDING_DELIVERY_STATUS = 'CLARIFICATION_ASKED_FOR_READY_DEV3_NO_ANSWER_YET'
AUTHORIZED_DELIVERY_STATUS = 'AUTHORIZED_ONE_SHOT'
CONSUMED_DELIVERY_STATUS = 'CONSUMED_ONE_SHOT'
DELIVERY_STATUSES = {PENDING_DELIVERY_STATUS, AUTHORIZED_DELIVERY_STATUS, CONSUMED_DELIVERY_STATUS}
SHA40 = re.compile(r'^[0-9a-f]{40}$')


def read_json(name):
    return json.loads((DOCS / name).read_text(encoding='utf-8'))


def read_bos3_json(name):
    return json.loads((BOS3_DOCS / name).read_text(encoding='utf-8'))


def require_false_readiness(failures, label, readiness):
    if not isinstance(readiness, dict):
        failures.append(f'Missing readiness contract: {label}')
        return
    for key in ('technical_ready', 'pilot_allowed', 'mvp'):
        if readiness.get(key) is not False:
            failures.append(f'Readiness must stay false: {label}.{key}')


def is_nonempty_string(value):
    return isinstance(value, str) and bool(value)


def require_full_pin(failures, label, value):
    if not is_nonempty_string(value) or not SHA40.fullmatch(value):
        failures.append(f'Invalid full commit pin: {label}')
        return False
    return True


def deadline_value(weekly):
    try:
        zone = ZoneInfo(weekly['timezone'])
        deadline = datetime.fromisoformat(weekly['deadline_local'])
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError('Invalid weekly execution deadline') from exc
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise ValueError('Weekly execution deadline must be timezone-aware')
    local_deadline = deadline.astimezone(zone)
    if local_deadline.utcoffset() != deadline.utcoffset():
        raise ValueError('Weekly execution deadline offset does not match its timezone')
    return local_deadline


def cutoff_reached(weekly, now=None):
    if not isinstance(weekly, dict):
        return None
    deadline = deadline_value(weekly)
    current = datetime.now(deadline.tzinfo) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError('Current cutoff time must be timezone-aware')
    return current.astimezone(deadline.tzinfo) >= deadline


def bos3_cards(state):
    cards = state.get('cards')
    if not isinstance(cards, list):
        raise ValueError('Missing current BoS 3 cards')
    return cards


def is_active_card_status(status):
    return (isinstance(status, str)
            and any(status == marker or status.startswith(marker + '_')
                    for marker in ACTIVE_CARD_MARKERS))


def validate_weekly_execution(failures, weekly, cards, delivery_status):
    if not isinstance(weekly, dict):
        failures.append('Weekly execution contract must be an object')
        return
    try:
        deadline_value(weekly)
    except ValueError as exc:
        failures.append(str(exc))
    if weekly.get('changes_after_deadline_allowed') is not False:
        failures.append('Weekly execution must forbid changes after deadline')
    if weekly.get('workflow') != 'DEVELOPMENT_WORKFLOW_RU.md':
        failures.append('Unexpected weekly workflow contract')
    if not isinstance(weekly.get('goal_owner_thread_id'), str) or not weekly['goal_owner_thread_id']:
        failures.append('Missing weekly goal owner thread')
    workers = weekly.get('max_active_workers')
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 4:
        failures.append('Weekly worker limit must be between 1 and 4')
    if weekly.get('integrator_count') != 1:
        failures.append('Weekly execution requires exactly one integrator')
    next_card_id = weekly.get('next_product_card')
    next_status = weekly.get('next_product_status')
    if next_card_id is None:
        if delivery_status != CONSUMED_DELIVERY_STATUS:
            failures.append('Only consumed delivery may have no automatic next card')
        if next_status is not None:
            failures.append('Absent next card requires null next status')
    elif not is_nonempty_string(next_card_id):
        failures.append('Weekly next product card must be a current card ID or null')
    else:
        target = cards.get(next_card_id)
        if target is None:
            failures.append('Weekly next product card is not current')
        elif next_status != target.get('status'):
            failures.append('Weekly next product status differs from current card')
    if delivery_status == PENDING_DELIVERY_STATUS:
        if next_card_id != 'B30-PREVIEW-DELIVERY' or next_status != 'BLOCKED':
            failures.append('Pending preview delivery must keep next delivery BLOCKED')
    if weekly.get('decision_owner') != 'owner':
        failures.append('Weekly decision owner must be owner')
    if weekly.get('post_deadline_actions') != ['read', 'report', 'pause_automation']:
        failures.append('Unexpected post-deadline actions')
    priorities = weekly.get('priorities')
    if not isinstance(priorities, list) or [item.get('rank') if isinstance(item, dict) else None
                                           for item in priorities] != [1, 2, 3, 4, 5]:
        failures.append('Weekly priorities must use ordered ranks 1 through 5')
        return
    for priority in priorities:
        if priority.get('status') not in BLOCKED_PRIORITY_STATUSES:
            failures.append(f"Invalid weekly priority status: {priority.get('rank')}")
        if priority.get('status') == 'BLOCKED':
            for field in ('blocker', 'decision_owner', 'next_action'):
                if not isinstance(priority.get(field), str) or not priority[field]:
                    failures.append(f"Blocked priority lacks {field}: {priority.get('rank')}")
        if priority.get('status') == 'DONE' and not is_nonempty_string(priority.get('evidence')):
            failures.append(f"Done priority lacks evidence: {priority.get('rank')}")


def validate_delivery_record(failures, delivery, candidate_pin, cards):
    if not isinstance(delivery, dict) or delivery.get('status') not in DELIVERY_STATUSES:
        failures.append('Invalid preview delivery recorded status')
        return None
    status = delivery['status']
    if status == PENDING_DELIVERY_STATUS:
        delivery_card = cards.get('B30-PREVIEW-DELIVERY')
        if delivery_card is None or delivery_card.get('status') != 'BLOCKED':
            failures.append('Pending preview delivery card must stay BLOCKED')
        return status
    authorization = delivery.get('authorization_record')
    if (not isinstance(authorization, dict)
            or not is_nonempty_string(authorization.get('owner_message_ref'))
            or authorization.get('exact_product_pin') != candidate_pin
            or authorization.get('scope') != 'owner_local_update_and_entry_only'):
        failures.append('Invalid preview delivery authorization record')
    if status == CONSUMED_DELIVERY_STATUS:
        if delivery.get('consumed_attempts') != 1:
            failures.append('Consumed preview delivery must record exactly one attempt')
        if not is_nonempty_string(delivery.get('result_record')):
            failures.append('Consumed preview delivery lacks result record')
        if delivery.get('outcome') not in {'PASS_SCOPED', 'FAIL', 'INCOMPLETE'}:
            failures.append('Consumed preview delivery has invalid outcome')
    return status


def validate_bos3():
    failures = []
    state = read_bos3_json('CONTROL_STATE.json')
    candidate = read_bos3_json('LIGHT_PREVIEW_CANDIDATE.json')
    runtime = read_bos3_json('LOCAL_RUNTIME_RECEIPT.json')
    cards = bos3_cards(state)
    ids = [card.get('id') for card in cards if isinstance(card, dict)]
    if len(ids) != len(cards) or any(not isinstance(card_id, str) or not card_id for card_id in ids):
        failures.append('Invalid current card IDs')
    elif len(set(ids)) != len(ids):
        failures.append('Duplicate active card IDs')
    historical = state.get('historical_cards')
    if state.get('historical_cards_current_assignments') is not False or not isinstance(historical, list):
        failures.append('Historical cards must not dispatch current assignments')
    elif set(ids) & {card.get('id') for card in historical if isinstance(card, dict)}:
        failures.append('Historical cards overlap current assignments')
    current_cards = {card['id']: card for card in cards
                     if isinstance(card, dict) and is_nonempty_string(card.get('id'))}
    for card in cards:
        if not isinstance(card, dict):
            continue
        if is_active_card_status(card.get('status')):
            owner = card.get('owner') or card.get('owner_thread')
            reviewer = card.get('reviewer') or card.get('reviewer_thread')
            if not isinstance(owner, str) or not owner:
                failures.append(f"Active card lacks owner: {card.get('id')}")
            if not isinstance(reviewer, str) or not reviewer:
                failures.append(f"Active card lacks reviewer: {card.get('id')}")
            elif reviewer == owner:
                failures.append(f"Active card owner and reviewer match: {card.get('id')}")
    state_product_pin = state.get('product_candidate_commit')
    candidate_pin = candidate.get('product_commit')
    state_runtime_pin = state.get('runtime_source_commit')
    runtime_pin = runtime.get('source_commit')
    require_full_pin(failures, 'state.product_candidate_commit', state_product_pin)
    require_full_pin(failures, 'candidate.product_commit', candidate_pin)
    require_full_pin(failures, 'state.runtime_source_commit', state_runtime_pin)
    require_full_pin(failures, 'runtime.source_commit', runtime_pin)
    if state_product_pin != candidate_pin:
        failures.append('Product candidate pin differs from manifest')
    if not is_nonempty_string(state.get('candidate_version')):
        failures.append('Invalid candidate version in state')
    if not is_nonempty_string(candidate.get('version')):
        failures.append('Invalid candidate version in manifest')
    if state.get('candidate_version') != candidate.get('version'):
        failures.append('Product candidate version differs from manifest')
    if state.get('candidate_manifest') != 'LIGHT_PREVIEW_CANDIDATE.json':
        failures.append('Unexpected product candidate manifest')
    if not is_nonempty_string(state.get('delivered_runtime_version')):
        failures.append('Invalid delivered runtime version in state')
    if not is_nonempty_string(runtime.get('version')):
        failures.append('Invalid runtime version in receipt')
    if state_runtime_pin != runtime_pin:
        failures.append('Runtime source pin differs from receipt')
    if state.get('delivered_runtime_version') != runtime.get('version'):
        failures.append('Runtime version differs from receipt')
    require_false_readiness(failures, 'state', state.get('readiness'))
    require_false_readiness(failures, 'candidate', candidate.get('readiness'))
    require_false_readiness(failures, 'runtime', {
        key: runtime.get(key) for key in ('technical_ready', 'pilot_allowed', 'mvp')
    })
    delivery_status = validate_delivery_record(
        failures, state.get('light_preview_delivery_permission'), candidate_pin, current_cards
    )
    weekly = state.get('weekly_execution')
    if 'weekly_execution' in state:
        validate_weekly_execution(failures, weekly, current_cards, delivery_status)
    return {
        'scope': 'bos3 development control; not application acceptance',
        'result': 'FAIL' if failures else 'PASS',
        'active_card_count': len(cards),
        'historical_cards_dispatched': False,
        'product_candidate_commit': candidate.get('product_commit'),
        'runtime_source_commit': runtime.get('source_commit'),
        'readiness': state.get('readiness'),
        'application_tests_run': False,
        'cli_runtime_tested': False,
        'errors': failures,
    }


def bos3_status():
    state = read_bos3_json('CONTROL_STATE.json')
    weekly = state.get('weekly_execution')
    delivery = state.get('light_preview_delivery_permission', {})
    return {
        'scope': 'bos3 development control; read-only; not application acceptance',
        'phase': state.get('phase'),
        'product': {
            'candidate_version': state.get('candidate_version'),
            'candidate_commit': state.get('product_candidate_commit'),
            'evidence_status': state.get('evidence_packaging', {}).get('status'),
        },
        'runtime': {
            'delivered_version': state.get('delivered_runtime_version'),
            'source_commit': state.get('runtime_source_commit'),
            'receipt': state.get('runtime_receipt'),
        },
        'readiness': state.get('readiness'),
        'delivery': {
            'status': delivery.get('status'),
            'recorded_only': True,
        },
        'execution_authorized_by_tool': False,
        'requires_live_owner_instruction': True,
        'cutoff_reached': cutoff_reached(weekly),
    }


def bos3_main(parser, args):
    if args.command == 'validate':
        try:
            result = validate_bos3()
        except (OSError, KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            result = {'scope': 'bos3 development control; not application acceptance',
                      'result': 'FAIL', 'errors': [str(exc)]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['result'] == 'PASS' else 2
    if args.command == 'status':
        print(json.dumps(bos3_status(), ensure_ascii=False, indent=2))
    elif args.command == 'card':
        cards = {card.get('id'): card for card in bos3_cards(read_bos3_json('CONTROL_STATE.json'))
                 if isinstance(card, dict)}
        card = cards.get(args.task)
        if card is None:
            parser.error('Unknown current BoS 3 card ID')
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        name = 'TEAM_CURRENT_RU.md' if args.command == 'context' else 'ACTIVE_WORK_PLAN_RU.md'
        print((BOS3_DOCS / name).read_text(encoding='utf-8'), end='')
    return 0


def validate():
    failures = []
    state = read_json('STATE.json')
    queue = read_json('QUEUE.json')
    config = tomllib.loads((ROOT / '.codex/config.toml').read_text(encoding='utf-8'))
    roles = {k: v for k, v in config['agents'].items() if isinstance(v, dict)}
    tasks = {t['id']: t for t in queue['tasks']}
    if len(tasks) != len(queue['tasks']):
        failures.append('Duplicate task IDs')
    for name, role in roles.items():
        path = (ROOT / '.codex' / role['config_file']).resolve()
        if not path.is_relative_to(ROOT / '.codex/agents'):
            failures.append(f'Role path outside project agents: {name}')
            continue
        data = tomllib.loads(path.read_text(encoding='utf-8'))
        if data.get('name') != name or not data.get('developer_instructions'):
            failures.append(f'Invalid role contract: {name}')
        if data.get('sandbox_mode') not in ('read-only', 'workspace-write'):
            failures.append(f'Invalid role sandbox: {name}')
    visiting, visited = set(), set()

    def visit(task_id):
        if task_id in visiting:
            failures.append(f'Dependency cycle: {task_id}')
            return
        if task_id in visited:
            return
        if task_id not in tasks:
            failures.append(f'Missing dependency: {task_id}')
            return
        visiting.add(task_id)
        task = tasks[task_id]
        if task['owner'] not in roles:
            failures.append(f'Unknown role: {task_id}')
        for dep in task['depends_on']:
            visit(dep)
        if task.get('card') and not (ROOT / task['card']).is_file():
            failures.append(f'Missing card: {task_id}')
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
    if state['execution']['status'] == 'PAUSED_FOR_OWNER_PLAN_REVIEW':
        for name in ('product_execution_allowed', 'ci_allowed', 'deploy_allowed', 'paid_api_allowed'):
            if state['execution'][name] is not False:
                failures.append(f'Pause conflict: {name}')
        if queue['launch_gate'] != state['execution']['status']:
            failures.append('Queue pause differs from state')
    limits = state['historical_limits']
    if (limits['P05_timeout_cycle_used'], limits['P05_timeout_cycle_limit']) != (3, 3):
        failures.append('Historical attempt count changed')
    if any(limits[k] for k in limits if k.endswith('_allowed')):
        failures.append('Historical blocked action enabled')
    if state['technical_ready'] or state['pilot_allowed']:
        failures.append('Setup must not assert product readiness')
    if state['next_after_owner_review'] != 'P10-003':
        failures.append('Unexpected next card')
    tree = ast.parse((ROOT / 'scripts/verify.py').read_text(encoding='utf-8'))
    actual = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'GATES' for t in n.targets))
    frozen = read_json('ACCEPTANCE_GATES.json')['gates']
    if {str(k): v for k, v in actual.items()} != frozen or len(actual) != 11:
        failures.append('Acceptance GATES changed')
    return {'scope': 'static setup only; not application acceptance',
            'result': 'FAIL' if failures else 'PASS', 'role_count': len(roles),
            'task_count': len(tasks), 'gate_count': len(actual),
            'execution_status': state['execution']['status'],
            'application_tests_run': False, 'cli_runtime_tested': False,
            'errors': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('legacy', 'bos3'), default='legacy')
    parser.add_argument('command', choices=('status', 'context', 'plan', 'card', 'validate'))
    parser.add_argument('task', nargs='?')
    args = parser.parse_args()
    if args.scope == 'bos3':
        return bos3_main(parser, args)
    if args.command == 'validate':
        try:
            result = validate()
        except (OSError, KeyError, ValueError, SyntaxError) as exc:
            result = {'result': 'FAIL', 'errors': [str(exc)]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['result'] == 'PASS' else 2
    if args.command == 'status':
        print(json.dumps(read_json('STATE.json'), ensure_ascii=False, indent=2))
    elif args.command == 'card':
        tasks = {t['id']: t for t in read_json('QUEUE.json')['tasks']}
        task = tasks.get(args.task)
        if task is None:
            parser.error('Unknown task ID')
        if task.get('card'):
            print((ROOT / task['card']).read_text(encoding='utf-8'))
        else:
            print(json.dumps(task, ensure_ascii=False, indent=2))
    else:
        name = 'CONTEXT_UA.md' if args.command == 'context' else 'PLAN_UA.md'
        print((DOCS / name).read_text(encoding='utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
