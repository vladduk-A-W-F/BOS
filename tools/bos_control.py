"""Read-only BoS setup inspector. Does not start Django, agents, CI or APIs."""
import argparse
import ast
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'orchestration'


def read_json(name):
    return json.loads((DOCS / name).read_text(encoding='utf-8'))


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
    parser.add_argument('command', choices=('status', 'context', 'plan', 'card', 'validate'))
    parser.add_argument('task', nargs='?')
    args = parser.parse_args()
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
