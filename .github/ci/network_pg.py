"""NETWORK-PG: two new bounded PG16 concurrency scenarios, never a suite rerun."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
BRANCH = 'refs/heads/feat/network-operations-20260920'
REPOSITORY = 'vladduk-A-W-F/BOS'
TOKEN = '[bos-network-acceptance:20260920-01]'
# Root freezes this after integrating the independently reviewed runtime cards.
CANDIDATE_SOURCE = 'c15dfe0e3aeefde2fd4fa7af0e9dd2c7c04072a59b185554b821576b4c2111ca'
CI_PATHS = {'.github/ci/network_pg.py', '.github/workflows/bos-network-targeted.yml',
            '.github/ci/network_browser_acceptance.py'}
TESTS = ('test_transfer_receive_same_proposal_waits_and_has_one_effect',
         'test_retention_release_same_proposal_waits_and_has_one_effect')

spec = importlib.util.spec_from_file_location('network_pg_helpers', ROOT / '.github/ci/batch_01_targeted.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def finalize(output):
    output.mkdir(parents=True, exist_ok=True)
    if not (output / 'report.json').exists():
        h.write_json(output / 'report.json', dict(card='NETWORK-PG', status='BLOCKED_BEFORE_RUNNER',
            accepted_scoped=False, technical_ready=False, pilot_allowed=False, full_run=False,
            business_e2e_run=False, run_id=os.environ.get('GITHUB_RUN_ID'),
            run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT')))
    h.finalize(output)
    index = json.loads((output / 'sha256-index.json').read_text())
    index['schema'] = 'bos.network.pg.sha256.v1'
    h.write_json(output / 'sha256-index.json', index)


def guard():
    """A reviewed, clean, exact push candidate can execute only its first attempt."""
    if (os.environ.get('GITHUB_EVENT_NAME') != 'push' or os.environ.get('GITHUB_REF') != BRANCH
            or os.environ.get('GITHUB_REPOSITORY') != REPOSITORY
            or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'):
        raise ValueError('Only the approved repository, feature branch and first push attempt may run')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    commit = h.git(ROOT, 'rev-parse', 'HEAD')
    if (event.get('deleted') or event.get('forced') or event.get('ref') != BRANCH
            or event.get('repository', {}).get('full_name') != REPOSITORY
            or event.get('after') != commit or os.environ.get('GITHUB_SHA') != commit
            or os.environ.get('BOS_NETWORK_CANDIDATE_SHA') != commit
            or TOKEN not in event.get('head_commit', {}).get('message', '').splitlines()
            or TOKEN not in h.git(ROOT, 'log', '-1', '--format=%B').splitlines()):
        raise ValueError('Push identity or exact commit token differs from approval')
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Python 3.12 required')
    changed = set(h.git(ROOT, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD^', 'HEAD').splitlines())
    if not changed.intersection(CI_PATHS) or h.git(ROOT, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('A clean candidate with a changed CI allowlist path is required')
    digest = h.verifier(ROOT).source_digest()
    if not re.fullmatch('[a-f0-9]{64}', CANDIDATE_SOURCE) or digest != CANDIDATE_SOURCE:
        raise ValueError('Runtime does not match the independently reviewed and frozen candidate')
    return {'candidate_commit': commit, 'source_sha256': digest, 'changed_ci_paths': sorted(changed & CI_PATHS)}


def worker():
    """Tests are defined here so this harness never discovers historical modules."""
    from concurrent.futures import ThreadPoolExecutor
    from copy import deepcopy
    from decimal import Decimal as D
    import threading
    import unittest

    sys.path.insert(0, str(ROOT))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
    import django
    django.setup()
    from django.db import connection, connections, transaction
    from django.test import Client, TransactionTestCase, override_settings
    from django.test.runner import DiscoverRunner
    from erp.test_corrections import CorrectionFixture
    from erp.models import Event, Location, Lot, Movement, PaymentRetention, StockTransfer
    from erp.balances import invoice_settlement
    from operations.models import ActionProposal, Invoice
    from finance.models import FinancialIntent, Transaction

    @override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                       PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
    class NetworkConcurrencyTests(CorrectionFixture, TransactionTestCase):
        databases = {'default'}

        def setUp(self):
            self.assertEqual(connection.vendor, 'postgresql', 'SQLite cannot prove PostgreSQL contention')
            super().setUp()
            # Reuse the established synthetic fixture, explicitly selecting UAH.
            self.f = self.fixture('NETWORK-UAH', 'UAH')
            self.destination = Location.objects.create(code='NPG-DEST', name='Synthetic destination')

        def state(self):
            return super().state() | {
                m._meta.label: list(m.objects.order_by('pk').values())
                for m in (StockTransfer, PaymentRetention, Invoice, Transaction, FinancialIntent)}

        def twin(self):
            client = Client(enforce_csrf_checks=True, raise_request_exception=False)
            client.cookies = deepcopy(self.http.cookies)
            return client

        def held_pair(self, proposal, action):
            held = threading.Event()
            release = threading.Event()
            attempted = threading.Event()
            done = threading.Event()
            pids = {}
            before = self.state()
            clients = (self.twin(), self.twin())
            proof = None

            def prepare_connection(kind):
                connections.close_all()
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute('SELECT pg_backend_pid()')
                    pids[kind] = cursor.fetchone()[0]

            def holder():
                try:
                    prepare_connection('holder')
                    # The real HTTP writer owns the normal ERP lock, retained
                    # until this outer transaction commits. Nothing is mocked.
                    with transaction.atomic():
                        response = self.confirm(proposal, clients[0])
                        self.assertEqual(response.status_code, 200, response.content)
                        held.set()
                        if not release.wait(12):
                            raise RuntimeError('Held writer release timeout')
                    return {'status': response.status_code, 'json': response.json()}
                finally:
                    connections.close_all()

            def waiter():
                def observe(execute, sql, params, many, context):
                    if sql.lstrip().upper().startswith('UPDATE') and 'operations_configuration' in sql:
                        attempted.set()
                    return execute(sql, params, many, context)
                try:
                    prepare_connection('waiter')
                    with connection.execute_wrapper(observe):
                        response = self.confirm(proposal, clients[1])
                    return {'status': response.status_code, 'json': response.json()}
                finally:
                    done.set()
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(holder)
                second = None
                try:
                    if not held.wait(10):
                        if first.done():
                            first.result()  # retain the actual HTTP/SQL failure
                        self.fail('First HTTP confirm did not reach a held successful transaction')
                    second = pool.submit(waiter)
                    self.assertTrue(attempted.wait(5), 'Second confirm did not reach the real ERP mutex UPDATE')
                    # A separate live PG connection proves the actual blocking
                    # relation, not merely an elapsed-time/thread heuristic.
                    with h.pg_connect(os.environ, connection.settings_dict['NAME']) as observer:
                        observer.execute("SET statement_timeout = '2s'")
                        observer_pid = observer.execute('SELECT pg_backend_pid()').fetchone()[0]
                        self.assertNotIn(observer_pid, pids.values())
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            row = observer.execute(
                                'SELECT pg_blocking_pids(pid), wait_event_type, wait_event, query '
                                'FROM pg_stat_activity WHERE pid = %s', (pids['waiter'],)).fetchone()
                            if row and pids['holder'] in row[0] and row[1] == 'Lock':
                                self.assertIn('operations_configuration', row[3])
                                self.assertTrue(row[3].lstrip().upper().startswith('UPDATE'), row[3])
                                proof = {'action': action, 'proposal_id': proposal,
                                    'holder_pid': pids['holder'], 'waiter_pid': pids['waiter'],
                                    'observer_pid': observer_pid, 'blocking_pids': row[0],
                                    'wait_event_type': row[1], 'wait_event': row[2],
                                    'query': row[3], 'actual_vendor': connection.vendor}
                                break
                            if done.is_set():
                                break
                            time.sleep(.025)
                    self.assertIsNotNone(proof, 'PG did not expose waiter blocked by the held ERP writer')
                    self.assertFalse(done.is_set(), 'Waiter completed while the holder still owned the mutex')
                    self.assertEqual(self.state(), before, 'Uncommitted business effect became visible')
                    self.assertIsNone(ActionProposal.objects.get(pk=proposal).receipt)
                finally:
                    release.set()
                results = [first.result(timeout=20), second.result(timeout=20)]
            self.assertEqual([row['status'] for row in results], [200, 200], results)
            self.assertEqual(results[0]['json'], results[1]['json'])
            proof.update(statuses=[200, 200], equal_receipts=True, uncommitted_effect_hidden=True)
            return results[0]['json'], proof

        def prove_replay(self, proposal, receipt, proof):
            before = self.state()
            stored = ActionProposal.objects.get(pk=proposal).receipt
            response = self.confirm(proposal)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json(), receipt)
            self.assertEqual(self.state(), before)
            self.assertEqual(ActionProposal.objects.get(pk=proposal).receipt, stored)
            proof.update(one_effect=True, replay_unchanged=True, currency='UAH')
            print('BOS_NETWORK_LOCK ' + json.dumps(proof, ensure_ascii=False), flush=True)

        def test_transfer_receive_same_proposal_waits_and_has_one_effect(self):
            opening = self.act('opening', code='NPG-OPEN', item_id=self.f.item.pk,
                location_id=self.location.pk, quantity='10.000', unit_cost='3.33', currency='UAH',
                revision='A', reason='Synthetic network stock')
            self.act('quality', lot_id=opening['lot_id'], result='approved',
                inspector_id=self.owner.pk, note='Synthetic physical inspection')
            dispatched = self.act('transfer_dispatch', lot_id=opening['lot_id'], quantity='3.000',
                location_id=self.destination.pk, code='NPG-TRANSFER', reason='Synthetic replenishment')
            transfer = StockTransfer.objects.get(pk=dispatched['transfer_id'])
            proposal = self.preview({'action': 'erp_transfer_receive', 'transfer_id': transfer.pk,
                'code': 'NPG-ARRIVAL', 'reason': 'Synthetic physical arrival'})
            counts = (Event.objects.count(), Movement.objects.count(), Lot.objects.count())
            receipt, proof = self.held_pair(proposal, 'erp_transfer_receive')
            transfer.refresh_from_db()
            arrived = Lot.objects.get(pk=transfer.received_lot_id)
            source = Lot.objects.get(pk=opening['lot_id'])
            self.assertEqual((Event.objects.count(), Movement.objects.count(), Lot.objects.count()),
                             tuple(value + 1 for value in counts))
            self.assertEqual(StockTransfer.objects.count(), 1)
            self.assertEqual(transfer.status, 'received')
            self.assertEqual(receipt['lot_id'], arrived.pk)
            self.assertEqual((source.quantity, arrived.quantity), (D('7.000'), D('3.000')))
            self.assertEqual((arrived.currency, arrived.quality, arrived.unit_cost), ('UAH', 'pending', D('3.33')))
            self.assertEqual(arrived.location_id, self.destination.pk)
            self.assertEqual(transfer.receipt_movement.cost, D('9.99'))
            self.assertEqual(transfer.receipt_movement.cost, transfer.dispatch_movement.cost)
            self.assertEqual(Event.objects.filter(action='erp_transfer_receive').count(), 1)
            self.prove_replay(proposal, receipt, proof)

        def test_retention_release_same_proposal_waits_and_has_one_effect(self):
            order, _, _, _ = self.sale(shipped='10.000', quantity='10.000', price='10.00', currency='UAH')
            invoice_id = self.act('invoice', order_id=order.pk, code='NPG-INVOICE', due_date='2026-10-01')['invoice_id']
            held = self.act('hold_payment', invoice_id=invoice_id, amount='30.00', code='NPG-HOLD',
                            reason='Synthetic contractual guarantee')
            invoice = Invoice.objects.get(pk=invoice_id)
            self.assertEqual(invoice_settlement(invoice)['collectible'], D('70.00'))
            proposal = self.preview({'action': 'erp_release_payment', 'retention_id': held['retention_id'],
                                     'reason': 'Synthetic acceptance confirmed'})
            events = Event.objects.count()
            cash = list(Transaction.objects.order_by('pk').values())
            intents = list(FinancialIntent.objects.order_by('pk').values())
            receipt, proof = self.held_pair(proposal, 'erp_release_payment')
            retention = PaymentRetention.objects.get(pk=held['retention_id'])
            invoice.refresh_from_db()
            self.assertEqual(PaymentRetention.objects.count(), 1)
            self.assertEqual(retention.status, 'released')
            self.assertIsNotNone(retention.released_at)
            self.assertEqual(Event.objects.count(), events + 1)
            self.assertEqual(Event.objects.filter(action='erp_release_payment').count(), 1)
            self.assertEqual(invoice.paid, D('0.00'))
            settlement = invoice_settlement(invoice)
            self.assertEqual((settlement['receivable'], settlement['retained'], settlement['collectible']),
                             (D('100.00'), D('0.00'), D('100.00')))
            self.assertEqual(list(Transaction.objects.order_by('pk').values()), cash)
            self.assertEqual(list(FinancialIntent.objects.order_by('pk').values()), intents)
            self.prove_replay(proposal, receipt, proof)

    class ExactRunner(DiscoverRunner):
        def build_suite(self, test_labels=None, **kwargs):
            suite = unittest.TestSuite(NetworkConcurrencyTests(name) for name in TESTS)
            if suite.countTestCases() != 2:
                raise RuntimeError('Only the two new network concurrency methods are permitted')
            return suite

        def setup_databases(self, **kwargs):
            config = super().setup_databases(**kwargs)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_setting('server_version_num')")
                name, version = cursor.fetchone()
            proof = {'vendor': connection.vendor, 'database': name, 'version_num': int(version)}
            print('BOS_BATCH_TEST_DATABASE ' + json.dumps(proof), flush=True)
            if (connection.vendor != 'postgresql' or not 160000 <= int(version) < 170000
                    or name != 'test_' + os.environ['BOS_TEST_DB_NAME']):
                raise RuntimeError('Unexpected database or PostgreSQL version')
            return config

    return int(bool(ExactRunner(verbosity=2, interactive=False).run_tests([])))


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    marker = output / 'runner-started.json'
    if marker.exists():
        raise ValueError('Refuse a repeated execution in this evidence directory')
    h.write_json(marker, {'started_at': h.now()})
    report = dict(card='NETWORK-PG', scope='two new held network confirmations with actual PG lock observation',
        accepted_scoped=False, technical_ready=False, pilot_allowed=False, full_run=False,
        business_e2e_run=False, historical_p05_used=3, historical_p05_limit=3,
        A09_retried=False, A10_retried=False, A11_retried=False, errors=[], started_at=h.now(),
        run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
        python=platform.python_version(), harness_sha256=h.sha(Path(__file__)),
        helper_sha256=h.sha(Path(h.__file__)), runner_timeout_seconds=180)
    stage = dict(label='network-pg-two-locks', mode='postgres16', expected_tests=2, expected_red=None,
                 tests=list(TESTS), exit_code=None, status='NOT_RUN', accepted=False)
    report['checks'] = [stage]
    before = None
    try:
        report.update(guard())
        before = dict(source_sha256=h.verifier(ROOT).source_digest(), source_databases=h.source_databases(ROOT))
        report['source_before'] = before
        with h.pg_connect(os.environ, 'postgres') as db:
            report['postgres_version_num'] = int(db.execute('SHOW server_version_num').fetchone()[0])
            report['postgres_version'] = db.execute('SELECT version()').fetchone()[0]
        if not 160000 <= report['postgres_version_num'] < 170000:
            raise ValueError('PostgreSQL 16 required')
        with tempfile.TemporaryDirectory(prefix='bos-network-pg-') as directory:
            work = Path(directory)
            (work / 'media').mkdir(mode=0o700)
            (work / 'source').mkdir()
            # Existing approved allocator is responsible for CREATE/DROP.
            with h.verifier(ROOT).database('postgres', work) as env:
                stage['source_database'] = env['BOS_TEST_DB_NAME']
                stage['source_canary_before'] = h.source_canary(env, create=True)
                env.update(DJANGO_SETTINGS_MODULE='verification_settings',
                    PYTHONDONTWRITEBYTECODE='1', BOS_NETWORK_PG_WORKER='1')
                for key in ('GITHUB_TOKEN', 'GH_TOKEN'):
                    env.pop(key, None)
                stage.update(status='RUNNING', started_at=h.now())
                stage['command'] = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker']
                h.write_json(output / 'report.json', report)
                try:
                    with (output / 'postgres.stdout.log').open('w') as stdout, (output / 'postgres.stderr.log').open('w') as stderr:
                        try:
                            result = subprocess.run(stage['command'], cwd=ROOT, env=env, stdout=stdout,
                                                    stderr=stderr, timeout=180)
                            stage['exit_code'] = result.returncode
                        except subprocess.TimeoutExpired:
                            stage['timed_out'] = True
                finally:
                    try:
                        stage['source_canary_after'] = h.source_canary(env)
                        stage['source_database_unchanged'] = stage['source_canary_before'] == stage['source_canary_after']
                    finally:
                        # Django normally removes this DB. A killed/timed-out
                        # worker must not leave its issued test DB behind.
                        from psycopg import sql
                        issued = env['BOS_TEST_DB_NAME']
                        if not re.fullmatch(r'bos_verify_[a-f0-9]{16}', issued):
                            raise ValueError('Refuse cleanup of an unissued database')
                        with h.pg_connect(env, 'postgres') as admin:
                            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(
                                sql.Identifier('test_' + issued)))
                            stage['test_database_cleanup_verified'] = admin.execute(
                                'SELECT count(*) FROM pg_database WHERE datname = %s', ('test_' + issued,)).fetchone()[0] == 0
        stdout = (output / 'postgres.stdout.log').read_text()
        stderr = (output / 'postgres.stderr.log').read_text()
        locks = [json.loads(line.partition(' ')[2]) for line in stdout.splitlines() if line.startswith('BOS_NETWORK_LOCK ')]
        stage['lock_proofs'] = locks
        locks_proven = len(locks) == 2 and {x['action'] for x in locks} == {'erp_transfer_receive', 'erp_release_payment'}
        locks_proven = locks_proven and all(x['holder_pid'] in x['blocking_pids'] and x['wait_event_type'] == 'Lock'
            and len({x['holder_pid'], x['waiter_pid'], x['observer_pid']}) == 3
            and x['one_effect'] and x['replay_unchanged'] and x['equal_receipts']
            and x['uncommitted_effect_hidden'] and x['actual_vendor'] == 'postgresql' for x in locks)
        stage['accepted'] = bool(h.evaluate(stage, stdout, stderr) and stage['source_database_unchanged']
                                 and stage['test_database_cleanup_verified'] and locks_proven)
        stage['status'] = 'PASS_SCOPED' if stage['accepted'] else 'FAIL'
        report['accepted_scoped'] = stage['accepted']
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        (output / 'runner.exception.log').write_text(traceback.format_exc())
    finally:
        after = dict(source_sha256=h.verifier(ROOT).source_digest(), source_databases=h.source_databases(ROOT))
        report['source_unchanged'] = before is not None and before == after
        report['accepted_scoped'] = bool(report['accepted_scoped'] and report['source_unchanged'] and not report['errors'])
        report.update(status='PASS_SCOPED' if report['accepted_scoped'] else 'FAIL_OR_BLOCKED', completed_at=h.now())
        h.write_json(output / 'report.json', report)
        finalize(output)
        print('BOS_NETWORK_PG_RESULT ' + json.dumps({
            'status': report['status'], 'accepted_scoped': report['accepted_scoped'],
            'candidate_commit': report.get('candidate_commit'), 'source_sha256': report.get('source_sha256'),
            'postgres_version_num': report.get('postgres_version_num'),
            'source_unchanged': report['source_unchanged'], 'exit_code': stage['exit_code'],
            'observed_test_counts': stage.get('observed_test_counts', []),
            'test_database_cleanup_verified': stage.get('test_database_cleanup_verified', False),
            'locks': [{key: proof.get(key) for key in ('action', 'actual_vendor', 'wait_event_type',
                       'holder_pid', 'waiter_pid', 'observer_pid', 'blocking_pids', 'statuses',
                       'one_effect', 'replay_unchanged')} for proof in stage.get('lock_proofs', [])],
            'errors': report['errors'], 'technical_ready': False, 'pilot_allowed': False},
            ensure_ascii=False), flush=True)
    return 0 if report['accepted_scoped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--finalize-only', action='store_true')
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        if os.environ.get('BOS_NETWORK_PG_WORKER') != '1':
            parser.error('Worker requires the guarded parent process')
        raise SystemExit(worker())
    if args.output is None:
        parser.error('--output is required')
    if args.finalize_only:
        finalize(args.output.resolve())
    else:
        raise SystemExit(run(args.output.resolve()))
