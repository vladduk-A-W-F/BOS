"""Gate 5: execute the frozen A06 concurrency suite on a new synthetic DB.

The manifest is reviewed input, never inferred from current discovered tests.
SQLite and PostgreSQL are separate executions. No absent backend earns a pass.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import sys
import threading
import traceback
import unittest


MIN_METHODS = 109
EXPECTED_SCHEMAS = 35
EXPECTED_ERP_RUNS = 116


def args_for_run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('concurrency_manifest.json'))
    parser.add_argument('--output', type=Path)
    return parser.parse_args()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def flatten(suite):
    if isinstance(suite, unittest.TestCase):
        yield suite
    else:
        for child in suite:
            yield from flatten(child)


class RealStdout(io.TextIOBase):
    """Forward real output and associate each complete line with its test."""
    def __init__(self, target, state):
        self.target = target
        self.state = state
        self.lock = threading.RLock()
        self.pending = ''
        self.pending_owner = None
        self.lines = []
        self.sha = hashlib.sha256()
        self.byte_count = 0

    @property
    def encoding(self):
        return getattr(self.target, 'encoding', 'utf-8')

    def writable(self):
        return True

    def write(self, value):
        with self.lock:
            self.target.write(value)
            encoded = value.encode('utf-8', errors='replace')
            self.sha.update(encoded)
            self.byte_count += len(encoded)
            pieces = value.splitlines(keepends=True)
            for piece in pieces:
                if not self.pending:
                    self.pending_owner = self.state.get('active_test_id')
                elif self.pending_owner != self.state.get('active_test_id'):
                    self.pending_owner = '<mixed-test-output>'
                self.pending += piece
                if self.pending.endswith('\n'):
                    self.lines.append((self.pending.rstrip('\r\n'), self.pending_owner))
                    self.pending = ''
            return len(value)

    def flush(self):
        with self.lock:
            self.target.flush()

    def finish(self):
        with self.lock:
            if self.pending:
                self.lines.append((self.pending, self.pending_owner))
                self.pending = ''
            self.target.flush()


def emit(report, output):
    value = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(value + '\n', encoding='utf-8')
    print(value, flush=True)
    return 0 if report['complete'] else 1


def validate_manifest(manifest):
    if manifest.get('schema') != 1 or manifest.get('gate') != 5:
        raise ValueError('Unsupported concurrency manifest schema/gate')
    baseline = manifest['baseline_a06']
    if hashlib.sha256(json.dumps(baseline,sort_keys=True,separators=(',',':')).encode()).hexdigest() != 'db06988865d19aff6aae73c1300c7127ff77df76a8c70a8ca3f5f1ab8c56f462':
        raise ValueError('The accepted A06 84-method/89-record/26-action baseline changed')
    for key in ('test_labels','required_test_ids','erp_schema_actions','required_erp_pass_records'):
        if any(entry not in manifest[key] for entry in baseline[key]):
            raise ValueError('An accepted A06 coverage entry was removed: '+key)
    for family, entries in baseline['erp_coverage_manifest'].items():
        if any(manifest['erp_coverage_manifest'][family].get(name) != entry for name,entry in entries.items()):
            raise ValueError('An accepted A06 ERP coverage oracle changed')
    b02=manifest['baseline_b02']
    if hashlib.sha256(json.dumps(b02,sort_keys=True,separators=(',',':')).encode()).hexdigest() != 'e81e275e15201edff254eebfd5c0aedd936e28f834205fba07e74f589dc3b78b':
        raise ValueError('The accepted B02 88-method/92-record/27-action baseline changed')
    for key in ('test_labels','required_test_ids','erp_schema_actions','required_erp_pass_records'):
        if any(entry not in manifest[key] for entry in b02[key]):raise ValueError('An accepted B02 coverage entry was removed: '+key)
    for family,entries in b02['erp_coverage_manifest'].items():
        if any(manifest['erp_coverage_manifest'][family].get(name)!=entry for name,entry in entries.items()):raise ValueError('An accepted B02 ERP coverage oracle changed')
    b03=manifest['baseline_b03']
    if hashlib.sha256(json.dumps(b03,sort_keys=True,separators=(',',':')).encode()).hexdigest() != '9cc4bcd8573b432d8d1806ff3067af49450a529335a5a46dbe4de998496894f4':
        raise ValueError('The accepted B03 99-method/110-record/33-action baseline changed')
    for key in ('test_labels','required_test_ids','erp_schema_actions','required_erp_pass_records'):
        if any(entry not in manifest[key] for entry in b03[key]):raise ValueError('An accepted B03 coverage entry was removed: '+key)
    for family,entries in b03['erp_coverage_manifest'].items():
        if any(manifest['erp_coverage_manifest'][family].get(name)!=entry for name,entry in entries.items()):raise ValueError('An accepted B03 ERP coverage oracle changed')
    c01=manifest['baseline_c01']
    if hashlib.sha256(json.dumps(c01,sort_keys=True,separators=(',',':')).encode()).hexdigest() != '0910ff83b62173df7eedfd4c1cfb1f52fefe178c265f3e2915d7fce6da9ee214':
        raise ValueError('The accepted C01 104-method/110-record/33-action baseline changed')
    for key in ('test_labels','required_test_ids','erp_schema_actions','required_erp_pass_records'):
        if any(entry not in manifest[key] for entry in c01[key]):raise ValueError('An accepted C01 coverage entry was removed: '+key)
    for family,entries in c01['erp_coverage_manifest'].items():
        if any(manifest['erp_coverage_manifest'][family].get(name)!=entry for name,entry in entries.items()):raise ValueError('An accepted C01 ERP coverage oracle changed')
    held=[{'currency':currency,'test_id':'finance.test_statement_concurrency.StatementConcurrencyTests.test_held_transaction_writes_serialize_before_reconcile_fingerprint_and_binding'} for currency in ('EUR','USD','UAH')]
    if manifest.get('required_c03_held_records')!=held:raise ValueError('Exactly three explicit C03 held-Transaction proofs are required')
    ids = manifest['required_test_ids']
    labels = manifest['test_labels']
    actions = manifest['erp_schema_actions']
    records = manifest['required_erp_pass_records']
    if len(ids) < MIN_METHODS or len(ids) != len(set(ids)):
        raise ValueError('Required test IDs must be unique and retain 104 old plus five C03 methods')
    if not labels or len(labels) != len(set(labels)):
        raise ValueError('Missing or duplicate test module labels')
    if any(not any(test_id.startswith(label + '.') for label in labels) for test_id in ids):
        raise ValueError('A required method is outside the explicitly selected modules')
    if len(actions) != EXPECTED_SCHEMAS or len(set(actions)) != EXPECTED_SCHEMAS:
        raise ValueError('Exactly 33 accepted plus two C03 ERP actions are required')
    keys = [(x['mode'], x['case'], x['currency']) for x in records]
    if len(keys) != EXPECTED_ERP_RUNS or len(set(keys)) != EXPECTED_ERP_RUNS:
        raise ValueError('Exactly 110 accepted plus six C03 currency records are required')
    if any(x['test_id'] not in ids or x['mode'] not in ('http', 'orm')
           or x['currency'] not in ('EUR', 'USD', 'UAH') for x in records):
        raise ValueError('ERP records must bind an explicit method/mode/currency')


def validate_database_env(root):
    backend = os.environ.get('BOS_VERIFY_DB', 'sqlite')
    name = os.environ.get('BOS_TEST_DB_NAME', '')
    if backend == 'sqlite':
        path = Path(name)
        if (not path.is_absolute() or not re.fullmatch(r'check_[a-f0-9]{32}\.sqlite3', path.name)
                or path.exists() or path.is_symlink() or path.resolve().is_relative_to(root)
                or not path.parent.is_dir()):
            raise ValueError('Refuse non-new/non-verify SQLite path; file-backed concurrency is mandatory')
        test_path = Path(str(path) + '_django_test')
        if test_path.exists() or test_path.is_symlink():
            raise ValueError('Refuse an existing Django SQLite test database; never auto-drop it')
    elif backend == 'postgres':
        if (os.environ.get('BOS_PG_DISPOSABLE') != '1'
                or not re.fullmatch(r'bos_verify_[a-f0-9]{16}', name)
                or not all(os.environ.get(k) for k in ('BOS_PGHOST', 'BOS_PGUSER', 'BOS_PGPASSWORD'))):
            raise ValueError('PostgreSQL needs an explicitly disposable isolated verify database')
    else:
        raise ValueError('Unsupported verification backend: ' + backend)
    media = os.environ.get('BOS_TEST_MEDIA', '')
    if not media or not Path(media).is_absolute() or Path(media).resolve().is_relative_to(root):
        raise ValueError('BOS_TEST_MEDIA must be an explicit absolute scratch path outside the checkout')
    return backend, name


def inspect_stdout(capture, manifest, report, fail):
    expected = {(r['mode'], r['case'], r['currency']): r
                for r in manifest['required_erp_pass_records']}
    records = []
    seen = Counter()
    for line, owner in capture.lines:
        if not line.startswith('A06_PASS '):
            continue
        try:
            value = json.loads(line[len('A06_PASS '):])
            if not isinstance(value, dict):
                raise ValueError('PASS record must be an object')
            mode = value.get('mode')
            case = value.get('action') if mode == 'http' else value.get('case')
            key = (mode, case, value.get('currency'))
            required = expected.get(key)
            records.append({'test_id': owner, 'record': value})
            seen[key] += 1
            if required is None:
                fail('erp_stdout', 'unexpected_mode_case_currency', record=value, test_id=owner)
                continue
            if owner != required['test_id']:
                fail('erp_stdout', 'pass_emitted_outside_required_test', expected=required['test_id'],
                     actual=owner, record=value)
            action = 'payment' if case == 'payment_dup' else case
            if (value.get('one_effect') is not True or value.get('inventory_id') != 'ERP-' + action
                    or type(value.get('erp_event_id')) is not int or value['erp_event_id'] <= 0):
                fail('erp_stdout', 'incomplete_effect_evidence', record=value, test_id=owner)
            if mode == 'http':
                statuses = value.get('statuses')
                if (not isinstance(statuses, list) or len(statuses) != 2 or 200 not in statuses
                        or any(type(s) is not int or s not in (200, 409) for s in statuses)
                        or value.get('replay_unchanged') is not True):
                    fail('erp_stdout', 'incomplete_concurrent_http_or_replay_evidence', record=value)
            elif value.get('loser_retry_rejected') is not True:
                fail('erp_stdout', 'missing_resource_retry_evidence', record=value)
        except (TypeError, ValueError, KeyError) as exc:
            fail('erp_stdout', 'malformed_pass_record', error=str(exc), line=line, test_id=owner)
    missing = [expected[key] for key in expected if seen[key] == 0]
    duplicates = [{'mode': key[0], 'case': key[1], 'currency': key[2], 'count': n}
                  for key, n in seen.items() if n > 1]
    report['erp_stdout'] = {'required': len(expected), 'observed': len(records),
        'unique': len(seen), 'missing': missing, 'duplicates': duplicates, 'records': records,
        'stdout_sha256': capture.sha.hexdigest(), 'stdout_bytes': capture.byte_count}
    if missing or duplicates or len(records) != len(expected):
        fail('erp_stdout', 'missing_duplicate_or_extra_pass_records', missing=len(missing),
             duplicates=len(duplicates), required=len(expected), observed=len(records))
    held_expected={row['currency']:row['test_id'] for row in manifest['required_c03_held_records']}
    held_records=[];held_seen=Counter()
    for line,owner in capture.lines:
        if not line.startswith('C03_HELD_TRANSACTION '):continue
        try:
            value=json.loads(line[len('C03_HELD_TRANSACTION '):]);currency=value['currency']
            held_records.append({'test_id':owner,'record':value});held_seen[currency]+=1
            vendor=report['database'].get('actual_vendor')
            lock_proofs=[value.get('first_lock',{}),value.get('reverse_lock',{})]
            lock_valid=all(p.get('uncommitted_business_not_visible') is True and
                (p.get('waited') is True or (vendor=='sqlite' and p.get('controlled_conflict_while_held') is True)) for p in lock_proofs)
            if (owner!=held_expected.get(currency) or value.get('actual_vendor')!=report['database'].get('actual_vendor')
                    or value.get('patch_then_reconcile_statuses')!=[200,409]
                    or value.get('reconcile_then_patch_statuses') not in ([[200,400],[200,409]] if vendor=='sqlite' else [[200,400]])
                    or value.get('bound_edit_retry_status')!=400 or not lock_valid
                    or any(value.get(key) is not True for key in ('stale_reconcile_refused','bound_source_edit_refused'))
                    or not any(x in value.get('first_trace',[]) for x in (('erp_mutex','transaction') if vendor=='sqlite' else ('transaction',)))
                    or 'transaction' not in value.get('reverse_trace',[])):
                fail('c03_held_transaction','incomplete_real_write_lock_evidence',record=value,test_id=owner)
        except (TypeError,ValueError,KeyError) as exc:
            fail('c03_held_transaction','malformed_record',error=str(exc),test_id=owner)
    report['c03_held_transaction']={'required':3,'records':held_records}
    if held_seen!=Counter({currency:1 for currency in held_expected}):
        fail('c03_held_transaction','missing_duplicate_or_extra_records',observed=dict(held_seen))


def main():
    args = args_for_run()
    report = {'schema': 1, 'gate': 5, 'date': datetime.now(timezone.utc).isoformat(),
              'complete': False, 'failures': [], 'tests': {}, 'database': {},
              'scope': 'Synthetic concurrency on the actual selected backend only; no browser/Windows/LLM acceptance.'}
    state = {'active_test_id': None, 'started': [], 'finished': [], 'succeeded': []}
    manifest = capture = runner = None
    source_paths = {}

    def fail(stage, detail, **fields):
        report['failures'].append({'stage': stage, 'detail': detail, **fields})

    try:
        if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
            raise ValueError('Assertions must not be disabled')
        root = args.project_root.resolve()
        if not root.is_dir():
            raise ValueError('Project root does not exist')
        backend, base_name = validate_database_env(root)
        sys.path.insert(0, str(root))
        os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
        os.environ['BOS_DATA_MODE'] = 'working'
        os.environ.pop('ANTHROPIC_API_KEY', None)
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        validate_manifest(manifest)
        report['manifest_sha256'] = digest(args.manifest)
        report['tests']['required_ids'] = manifest['required_test_ids']
        import django
        django.setup()
        from django.conf import settings
        from django.db import connection, connections
        from django.test import override_settings
        from django.test.runner import DiscoverRunner
        from scripts.check_support import prove_database
        from erp import service as erp_service
        erp_tests = importlib.import_module('erp.test_concurrency')
        statement_tests = importlib.import_module('finance.test_statement_concurrency')
        actual_actions = set(erp_service.SCHEMAS)
        required_actions = set(manifest['erp_schema_actions'])
        report['erp_schema'] = {'required': sorted(required_actions), 'actual': sorted(actual_actions)}
        if actual_actions != required_actions:
            fail('catalogue', 'erp_schema_actions_changed', missing=sorted(required_actions - actual_actions),
                 unexpected=sorted(actual_actions - required_actions))
        # Keep the original ERP test module's coverage dictionary unchanged;
        # the additive typed C03 HTTP writer owns its two explicit entries.
        combined_coverage=json.loads(json.dumps(erp_tests.COVERAGE_MANIFEST))
        if set(statement_tests.STATEMENT_COVERAGE_MANIFEST)!={'statement_import','statement_reconcile'}:
            fail('catalogue','unexpected_statement_coverage_actions')
        combined_coverage['erp_proposal_http'].update(statement_tests.STATEMENT_COVERAGE_MANIFEST)
        if combined_coverage != manifest['erp_coverage_manifest']:
            fail('catalogue', 'erp_test_coverage_manifest_changed')
        if set(connections) != {'default'} or str(connection.settings_dict['NAME']) != base_name:
            raise ValueError('Unexpected database alias or settings redirection')
        expected_vendor = 'postgresql' if backend == 'postgres' else 'sqlite'
        test_name = connection.creation._get_test_db_name()
        expected_test_name = base_name + '_django_test' if backend == 'sqlite' else 'test_' + base_name
        if str(test_name) != expected_test_name:
            raise ValueError('Unexpected Django test database destination')
        report['database'] = {'requested_backend': backend, 'base_name': base_name,
                              'expected_test_name': expected_test_name, 'actual_vendor': None}

        class TrackingResult(unittest.TextTestResult):
            def __init__(self, *values, **options):
                super().__init__(*values, **options)
                runner.gate_result = self

            def startTest(self, test):
                state['active_test_id'] = test.id()
                state['started'].append(test.id())
                super().startTest(test)

            def stopTest(self, test):
                state['finished'].append(test.id())
                state['active_test_id'] = None
                super().stopTest(test)

            def addSuccess(self, test):
                state['succeeded'].append(test.id())
                super().addSuccess(test)

        class GateRunner(DiscoverRunner):
            gate_result = None

            def get_resultclass(self):
                return TrackingResult

            def setup_databases(self, **kwargs):
                # Never permit DiscoverRunner's automatic destruction of an
                # existing test database, even in noninteractive mode.
                if backend == 'sqlite':
                    if Path(expected_test_name).exists() or Path(expected_test_name).is_symlink():
                        raise ValueError('Refuse existing SQLite test database before runner setup')
                else:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [expected_test_name])
                        if cursor.fetchone():
                            raise ValueError('Refuse existing PostgreSQL test database; no DROP allowed')
                previous = super().setup_databases(**kwargs)
                try:
                    if str(connection.settings_dict['NAME']) != expected_test_name:
                        raise ValueError('Runner did not use the approved synthetic test database')
                    prove_database()
                    if connection.vendor != expected_vendor:
                        raise ValueError('Actual test backend differs from requested backend')
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT sqlite_version()' if backend == 'sqlite' else 'SHOW server_version')
                        version = str(cursor.fetchone()[0])
                    report['database'].update(actual_vendor=connection.vendor,
                        actual_test_name=str(connection.settings_dict['NAME']), version=version,
                        engine_verified=True)
                except Exception:
                    super().teardown_databases(previous)
                    raise
                return previous

        runner = GateRunner(verbosity=1, interactive=False, keepdb=False, failfast=False,
                            buffer=False, parallel=0)
        suite = runner.build_suite(manifest['test_labels'])
        discovered = [test.id() for test in flatten(suite)]
        required = Counter(manifest['required_test_ids'])
        actual = Counter(discovered)
        report['tests'].update(labels=manifest['test_labels'], discovered_ids=discovered,
                              discovered=len(discovered))
        if actual != required:
            fail('catalogue', 'required_test_ids_changed', missing=list((required - actual).elements()),
                 unexpected=list((actual - required).elements()))
        if report['failures']:
            raise ValueError('Closed-world catalogue failed; incomplete suite is not executable acceptance')
        source_paths = {label: Path(importlib.import_module(label).__file__).resolve()
                        for label in manifest['test_labels']}
        if any(not path.is_relative_to(root) for path in source_paths.values()):
            raise ValueError('A test module was imported from outside the reviewed checkout')
        source_paths.update(verifier=Path(__file__), manifest=args.manifest,
                            erp_service=Path(erp_service.__file__))
        report['source_sha256_before'] = {name: digest(path) for name, path in source_paths.items()}
        capture = RealStdout(sys.stdout, state)
        with override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY=''), redirect_stdout(capture):
            prove_database()
            if connection.introspection.table_names():
                raise ValueError('Base verify database must be empty; refusing any existing application tables')
            returncode = runner.run_tests(manifest['test_labels'])
        report['runner_failures'] = returncode
        if returncode:
            fail('execution', 'django_runner_failed', runner_failures=returncode)
    except Exception as exc:
        fail('setup_or_execution', type(exc).__name__ + ': ' + str(exc), trace=traceback.format_exc())
    finally:
        if capture:
            capture.finish()

    if manifest is not None and 'required_test_ids' in manifest:
        required = Counter(manifest['required_test_ids'])
        for key in ('started', 'finished', 'succeeded'):
            values = Counter(state[key])
            report['tests'][key + '_ids'] = state[key]
            report['tests'][key] = len(state[key])
            if values != required:
                fail('execution', 'required_methods_not_' + key,
                     missing=list((required - values).elements()), unexpected=list((values - required).elements()))
    if runner is not None and runner.gate_result is not None:
        result = runner.gate_result
        report['tests']['tests_run'] = result.testsRun
        report['tests']['failures'] = [{'id': t.id(), 'trace': trace} for t, trace in result.failures]
        report['tests']['errors'] = [{'id': t.id(), 'trace': trace} for t, trace in result.errors]
        report['tests']['skipped'] = [{'id': t.id(), 'reason': reason} for t, reason in result.skipped]
        report['tests']['expected_failures'] = [{'id': t.id(), 'trace': trace} for t, trace in result.expectedFailures]
        report['tests']['unexpected_successes'] = [t.id() for t in result.unexpectedSuccesses]
        if (result.failures or result.errors or result.skipped or result.expectedFailures
                or result.unexpectedSuccesses or result.testsRun != len(manifest['required_test_ids'])):
            fail('execution', 'failed_skipped_xfail_or_unexecuted_methods')
    if capture is not None and manifest is not None:
        inspect_stdout(capture, manifest, report, fail)
    else:
        fail('erp_stdout', 'real_test_stdout_was_not_observed')
    if source_paths:
        try:
            report['source_sha256_after'] = {name: digest(path) for name, path in source_paths.items()}
            if report['source_sha256_after'] != report['source_sha256_before']:
                fail('provenance', 'reviewed_files_changed_during_execution')
        except Exception as exc:
            fail('provenance', type(exc).__name__ + ': ' + str(exc))
    report['complete'] = not report['failures'] and report['database'].get('engine_verified') is True
    return emit(report, args.output)


if __name__ == '__main__':
    raise SystemExit(main())
