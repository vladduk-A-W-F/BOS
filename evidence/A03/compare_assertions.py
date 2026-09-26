"""Read-only comparison of A03 auth bootstrap with the accepted test baseline."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/sites/bos-original-refined')
BASE = 'bcd5b9c'
OUT = Path('/workspace/scratch/c7b51e996a9f/tmp/a03_assertions_comparison.json')
SCRIPTS = [f'scripts/check_{name}.py' for name in ('workspace', 'erp', 'operations', 'original', 'launcher')]
TESTS = [
    'ai_assistant/tests.py', 'employees/tests.py', 'erp/tests.py',
    'finance/test_archive_regressions.py', 'finance/test_archive_stale.py',
    'finance/test_attribution_regressions.py', 'finance/test_finance_integrity.py',
    'finance/test_payment_integrity.py', 'finance/tests.py',
    'operations/test_reconciliation.py', 'tasks/tests.py',
]


def baseline(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT).decode()


def dump(node):
    return ast.dump(node, include_attributes=False)


class Assertions(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.rows = []
        self.tests = []

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        if node.name.startswith('test_'):
            self.tests.append('.'.join(self.scope))
        self.generic_visit(node)
        self.scope.pop()

    def visit_Assert(self, node):
        self.rows.append(('.'.join(self.scope), 'assert', dump(node)))
        self.generic_visit(node)

    def visit_Call(self, node):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == 'test':
            self.rows.append(('.'.join(self.scope), 'test(label, condition)', dump(node)))
        elif (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
              and fn.value.id == 'self' and fn.attr.startswith('assert')):
            self.rows.append(('.'.join(self.scope), 'self.' + fn.attr, dump(node)))
        self.generic_visit(node)


class StripExplicitAuthBootstrap(ast.NodeTransformer):
    """Only allow the observed standalone helper call and its import."""
    def visit_ImportFrom(self, node):
        if node.module in ('scripts.check_support', 'check_support'):
            node.names = [alias for alias in node.names if alias.name != 'login_test_client']
            if not node.names:
                return None
        return node

    def visit_Expr(self, node):
        if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                and node.value.func.id == 'login_test_client'):
            return None
        return self.generic_visit(node)


def collect(tree):
    visitor = Assertions()
    visitor.visit(tree)
    return visitor


def function(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


report = {'baseline': subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT).decode().strip(),
          'method': 'AST equality without line locations; assertion multiset includes scope and multiplicity; whole legacy AST equality after stripping only explicit auth imports/calls',
          'files': []}
ok = True
old_test_count = new_test_count = 0
for path in SCRIPTS + TESTS:
    before_src = baseline(path)
    after_src = (ROOT / path).read_text()
    before, after = ast.parse(before_src), ast.parse(after_src)
    old, new = collect(before), collect(after)
    lost = list((Counter(old.rows) - Counter(new.rows)).elements())
    added = list((Counter(new.rows) - Counter(old.rows)).elements())
    normalized = StripExplicitAuthBootstrap().visit(ast.parse(after_src))
    same_structure = dump(before) == dump(normalized)
    unchanged_assertions = not lost and not added
    old_test_count += len(old.tests)
    new_test_count += len(new.tests)
    row = {'file': path, 'assertions_before': len(old.rows), 'assertions_after': len(new.rows),
           'assertion_ast_unchanged': unchanged_assertions, 'removed_or_changed': lost,
           'added_assertions_in_legacy_file': added,
           'whole_ast_identical_after_auth_bootstrap_removed': same_structure,
           'test_names_before': old.tests, 'test_names_after': new.tests,
           'test_names_unchanged': old.tests == new.tests,
           'before_sha256': hashlib.sha256(before_src.encode()).hexdigest(),
           'after_sha256': hashlib.sha256(after_src.encode()).hexdigest()}
    report['files'].append(row)
    ok = ok and unchanged_assertions and same_structure and old.tests == new.tests

path = 'scripts/check_invariants.py'
before = ast.parse(baseline(path))
after = ast.parse((ROOT / path).read_text())
old, new = collect(before), collect(after)
anonymous_same = dump(function(before, 'client')) == dump(function(after, 'client'))

def remove_exact_statements(fn, code):
    targets = Counter(dump(node) for node in ast.parse(code).body)
    kept = []
    for node in fn.body:
        key = dump(node)
        if targets[key]:
            targets[key] -= 1
        else:
            kept.append(node)
    if any(targets.values()):
        raise AssertionError('Expected auth-only change is not present')
    fn.body = kept

remove_exact_statements(function(before, 'role_client'),
    "session = value.session\nsession['bos_role'] = role\nsession.save()")
remove_exact_statements(function(after, 'role_client'), "value.get('/api/operations/status/')")
invariant_result = {
    'file': path,
    'assertions_before': len(old.rows), 'assertions_after': len(new.rows),
    'assertion_ast_unchanged': Counter(old.rows) == Counter(new.rows),
    'anonymous_factory_ast_unchanged': anonymous_same,
    'whole_ast_identical_except_removal_of_manual_session_role_and_post_login_status_get': dump(before) == dump(after),
}
report['invariants'] = invariant_result
ok = ok and all(value for key, value in invariant_result.items() if isinstance(value, bool))

path = 'scripts/check_support.py'
before = ast.parse(baseline(path))
after = ast.parse((ROOT / path).read_text())
helper = function(after, 'login_test_client')
helper_assertions = collect(helper)
after.body.remove(helper)
report['helper'] = {'old_support_ast_unchanged': dump(before) == dump(after),
                    'new_helper_assertions': len(helper_assertions.rows),
                    'source': ast.unparse(helper)}
ok = ok and report['helper']['old_support_ast_unchanged']

report['legacy_test_method_counts'] = {'before': old_test_count, 'after': new_test_count}
report['legacy_runtime_counts_expected_unchanged'] = {'functional': 151, 'launcher': 5, 'django_unittest': 82}
report['complete'] = bool(ok and old_test_count == new_test_count == 82)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'complete': report['complete'], 'files': len(report['files']),
    'legacy_assertions_before': sum(row['assertions_before'] for row in report['files']),
    'legacy_assertions_after': sum(row['assertions_after'] for row in report['files']),
    'legacy_test_method_counts': report['legacy_test_method_counts'],
    'invariants': report['invariants'], 'helper_new_assertions': report['helper']['new_helper_assertions'],
    'report': str(OUT)}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report['complete'] else 1)
