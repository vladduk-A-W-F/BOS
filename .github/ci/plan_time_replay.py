"""PLAN-TIME diagnostic: one isolated PG16 replay sequence, never a gate PASS.

Run from the candidate runtime root. The supervisor must provide a newly created
disposable database and enforce a 60-second process deadline including imports,
connection, migrations and authentication. This worker creates no database and
does not change check_invariants.py or invoke its main function.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager, ExitStack
import cProfile
import faulthandler
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import re
import sys
import time
import traceback
from unittest.mock import patch


class Probe:
    def __init__(self, output, profile_enabled):
        self.output = output
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.current_phase = 'startup'
        self.functions = []
        self.sql_count = 0
        self.sql_seconds = 0.0
        self.report = {
            'schema': 1, 'diagnostic': 'PLAN-TIME/P06-F05/one-replay',
            'status': 'running', 'one_cycle_complete': False,
            'complete': False, 'root_cause_proven': False,
            'sequences': 0, 'replay_requests': 0,
            'gate_acceptance': False, 'historical_root_cause_proven': False,
            'technical_ready': False, 'pilot_allowed': False,
            'sequences_requested': 1, 'replays_requested': 4,
            'phases': [], 'calls': [], 'sql': {}, 'http_statuses': [],
            'instrumentation': {
                'cprofile_enabled': profile_enabled,
                'overhead': 'Uncalibrated observer overhead; instrumented wall time is not an uninstrumented benchmark.',
                'sql_timing_scope': 'cursor execute/executemany; fetch and Python materialization are outside SQL time',
                'function_timing_scope': 'inclusive; nested call times must not be added together',
                'hard_deadline': 'Supervisor must enforce 60 seconds including bootstrap.',
            },
            'limits': [
                'One synthetic sequence, not 1000 randomized sequences or five invariants.',
                'No historical phase timestamps; no attribution of the old 600-second timeout.',
                'One rollback proves no row growth for this sample only, not across 1000 cycles.',
                'No contending connection; measured mutex duration does not prove lock-wait behavior.',
            ],
        }
        self.sql = defaultdict(lambda: {'count': 0, 'seconds': 0.0, 'max_seconds': 0.0,
                                        'errors': 0, 'operations': Counter()})

    def save(self):
        self.report['elapsed_seconds'] = time.perf_counter() - self.started
        self.report['cpu_seconds'] = time.process_time() - self.cpu_started
        self.report['sql'] = dict(self.sql)
        self.report['sql_count'] = self.sql_count
        self.report['sql_seconds'] = self.sql_seconds
        temporary = self.output.with_suffix(self.output.suffix + '.tmp')
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.output)

    @contextmanager
    def phase(self, name):
        previous = self.current_phase
        self.current_phase = name
        wall, cpu = time.perf_counter(), time.process_time()
        queries, sql_seconds = self.sql_count, self.sql_seconds
        row = {'phase': name, 'started_seconds': wall - self.started, 'status': 'running'}
        self.report['phases'].append(row)
        print(json.dumps({'checkpoint': name, 'state': 'start', 'elapsed_seconds': wall-self.started}), flush=True)
        self.save()
        try:
            yield
            row['status'] = 'complete'
        except BaseException as exc:
            row['status'] = 'failed'
            row['exception_type'] = type(exc).__name__
            raise
        finally:
            row.update(wall_seconds=time.perf_counter()-wall, cpu_seconds=time.process_time()-cpu,
                       sql_count=self.sql_count-queries, sql_seconds=self.sql_seconds-sql_seconds)
            self.current_phase = previous
            self.save()
            print(json.dumps({'checkpoint': name, 'state': row['status'],
                              'wall_seconds': row['wall_seconds'], 'sql_count': row['sql_count']}), flush=True)

    def execute(self, execute, sql, params, many, context):
        started = time.perf_counter()
        key = self.current_phase + '/' + (self.functions[-1] if self.functions else 'other')
        row = self.sql[key]
        row['count'] += 1
        self.sql_count += 1
        row['operations'][str(sql).lstrip().split(None, 1)[0].upper() if str(sql).strip() else 'EMPTY'] += 1
        try:
            return execute(sql, params, many, context)
        except BaseException:
            row['errors'] += 1
            raise
        finally:
            elapsed = time.perf_counter() - started
            row['seconds'] += elapsed
            row['max_seconds'] = max(row['max_seconds'], elapsed)
            self.sql_seconds += elapsed

    def wrapped(self, name, original):
        @functools.wraps(original)
        def call(*args, **kwargs):
            started, cpu = time.perf_counter(), time.process_time()
            queries, sql_seconds = self.sql_count, self.sql_seconds
            row = {'function': name, 'phase': self.current_phase, 'status': 'running'}
            self.functions.append(name)
            try:
                result = original(*args, **kwargs)
                row['status'] = 'complete'
                return result
            except BaseException as exc:
                row.update(status='failed', exception_type=type(exc).__name__)
                raise
            finally:
                self.functions.pop()
                row.update(wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu,
                           sql_count=self.sql_count-queries, sql_seconds=self.sql_seconds-sql_seconds)
                self.report['calls'].append(row)
        return call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    probe = Probe(args.output, args.profile)
    profiler = cProfile.Profile() if args.profile else None
    faulthandler.enable()
    probe.report['faulthandler_after_seconds'] = min(45, max(.1, float(os.environ.get('BOS_PLAN_TIME_STACK_AFTER', '45'))))
    faulthandler.dump_traceback_later(probe.report['faulthandler_after_seconds'], repeat=False)
    if profiler:
        profiler.enable()
    try:
        with probe.phase('source_and_environment'):
            if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
                raise RuntimeError('Assertions must remain enabled')
            name = os.environ.get('BOS_TEST_DB_NAME', '')
            if (os.environ.get('DJANGO_SETTINGS_MODULE') != 'verification_settings'
                    or os.environ.get('BOS_VERIFY_DB') != 'postgres'
                    or os.environ.get('BOS_DATA_MODE') != 'demo'
                    or os.environ.get('BOS_PG_DISPOSABLE') != '1'
                    or not re.fullmatch(r'bos_verify_[0-9a-f]{16}', name)):
                raise RuntimeError('Explicit isolated PostgreSQL verification environment required')
            root = Path.cwd().resolve()
            paths = ['scripts/check_invariants.py', 'scripts/check_support.py',
                     'erp/service.py', 'erp/views.py', 'erp/queries.py',
                     'erp/adjustment_proposals.py', 'operations/service.py',
                     'boss_project/identity.py', 'boss_project/policy.py',
                     'demo_settings.py', 'verification_settings.py']
            probe.report['source_files_sha256'] = {
                path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in paths}
            probe.report['worker_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            probe.report['runtime'] = {'system': platform.system(), 'python': platform.python_version()}
            sys.path.insert(0, str(root))
            sys.path.insert(1, str(root/'scripts'))
        with probe.phase('django_setup'):
            import django
            django.setup()
            from django.db import connection, transaction
            from django.core.management import call_command
            probe.report['runtime']['django'] = django.get_version()
        with connection.execute_wrapper(probe.execute):
            with probe.phase('database_proof_before_writes'):
                if connection.vendor != 'postgresql':
                    raise RuntimeError('PostgreSQL required')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT current_database(), current_setting(\'server_version_num\'), current_setting(\'server_version\')')
                    actual, version_num, version = cursor.fetchone()
                    if actual != name or not 160000 <= int(version_num) < 170000:
                        raise RuntimeError('Assigned database and PostgreSQL 16 proof failed')
                    cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE'")
                    existing = cursor.fetchone()[0]
                    if existing:
                        raise RuntimeError('Refusing preexisting user tables; supervisor must supply an empty database')
                probe.report['database'] = {'vendor': connection.vendor, 'name': actual,
                                            'database': actual, 'version_num': int(version_num),
                                            'server_version': version, 'server_version_num': int(version_num),
                                            'preexisting_user_tables': existing}
            with probe.phase('migrate'):
                call_command('migrate', verbosity=0, interactive=False)
            # The existing helper module writes the settings environment and
            # reassigns DATABASES. Preserve the module environment and prove the
            # effective settings and live connection remain bound to the proof.
            with probe.phase('invariant_helpers_import_and_connection_recheck'):
                from django.conf import settings
                assert settings.SETTINGS_MODULE == 'verification_settings'
                settings_module = os.environ['DJANGO_SETTINGS_MODULE']
                critical_keys = ('ENGINE', 'NAME', 'HOST', 'PORT', 'USER', 'PASSWORD', 'OPTIONS')
                database_before = {key: settings.DATABASES['default'].get(key) for key in critical_keys}
                media_before = settings.MEDIA_ROOT
                live_connection_before = connection.connection
                try:
                    # Import only helpers; main (and its >=1000 gate) is never called.
                    from scripts import check_invariants as invariant
                finally:
                    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
                assert settings.SETTINGS_MODULE == 'verification_settings'
                assert {key: settings.DATABASES['default'].get(key) for key in critical_keys} == database_before
                assert settings.MEDIA_ROOT == media_before
                assert connection.connection is live_connection_before
                assert connection.vendor == 'postgresql' and connection.settings_dict['NAME'] == name
                with connection.cursor() as cursor:
                    cursor.execute('SELECT current_database(), current_setting(\'server_version_num\')')
                    confirmed_name, confirmed_version = cursor.fetchone()
                assert confirmed_name == actual and int(confirmed_version) == int(version_num)
                probe.report['helper_import_connection_proof_preserved'] = True
            from erp import service as erp, queries
            from erp.models import Item, Location, Lot, Movement, Event
            from operations.models import ActionProposal
            from django.apps import apps
            from decimal import Decimal

            def table_counts():
                # Auto-created M2M tables included. Sequence counters are not row data.
                models = {model._meta.db_table: model for model in apps.get_models(include_auto_created=True)
                          if model._meta.managed and not model._meta.proxy}
                return {table: model._base_manager.count() for table, model in sorted(models.items())}

            with probe.phase('synthetic_fixture'):
                area = Location.objects.create(code='INV-AREA', name='Synthetic diagnostic area', kind='production')
                Location.objects.create(code='INV-OTHER', name='Synthetic diagnostic other')
                raw = Item.objects.create(code='INV-RAW', name='Synthetic material', kind='material')
                Item.objects.create(code='INV-PRODUCT', name='Synthetic product', method='make')
                invariant.Employee.objects.create(full_name='Synthetic invariant operator',
                    phone='+000000000', email='synthetic@example.invalid')
            with probe.phase('role_authentication_once'):
                ceo = invariant.role_client('ceo')
            with probe.phase('counts_before_sequence'):
                counts_before = table_counts()
                probe.report['table_counts_before_sequence'] = counts_before
            with ExitStack() as stack:
                for owner, attribute, label in ((erp, 'fingerprint', 'global_fingerprint'),
                        (queries, 'snapshot', 'full_snapshot'), (erp, 'write_lock', 'erp_write_lock'),
                        (erp, 'dispatch', 'erp_dispatch')):
                    stack.enter_context(patch.object(owner, attribute, probe.wrapped(label, getattr(owner, attribute))))
                with transaction.atomic():
                    payload = {'action': 'erp_opening', 'code': 'INV-REPLAY', 'item_id': raw.pk,
                               'location_id': area.pk, 'quantity': '17', 'unit_cost': '13.07',
                               'currency': 'EUR', 'revision': 'A'}
                    with probe.phase('preview_opening'):
                        preview = invariant.post(ceo, '/api/erp/preview/', payload)
                        probe.report['http_statuses'].append({'request': 'preview', 'status': preview.status_code})
                        assert preview.status_code == 200, ('preview', preview.status_code)
                        confirmation = {'proposal_id': preview.json()['id'], 'confirmed': True}
                        assert ActionProposal.objects.get(pk=confirmation['proposal_id']).dependency_context is None
                    with probe.phase('first_confirm'):
                        first = invariant.post(ceo, '/api/operations/confirm/', confirmation)
                        probe.report['http_statuses'].append({'request': 'first_confirm', 'status': first.status_code})
                        assert first.status_code == 200, ('confirm', first.status_code)
                        receipt = first.json()
                    with probe.phase('unused_original_oracle'):
                        before = (erp.fingerprint(), Event.objects.count())
                    with probe.phase('interleaved_adjustment'):
                        erp.dispatch({'action': 'erp_adjust', 'lot_id': receipt['lot_id'],
                                      'delta': '3', 'reason': 'Synthetic next action'}, role='ceo')
                    with probe.phase('oracle_after_adjustment'):
                        before = (erp.fingerprint(), Event.objects.count())
                    for index in range(4):
                        with probe.phase('replay_http_' + str(index + 1)):
                            again = invariant.post(ceo, '/api/operations/confirm/', confirmation)
                            probe.report['http_statuses'].append({'request': 'replay_' + str(index + 1), 'status': again.status_code})
                            assert again.status_code == 200 and again.json() == receipt
                        with probe.phase('replay_oracle_' + str(index + 1)):
                            assert (erp.fingerprint(), Event.objects.count()) == before
                    with probe.phase('persisted_business_assertions'):
                        lot = Lot.objects.get(pk=receipt['lot_id'])
                        assert lot.quantity == Decimal('20')
                        assert Lot.objects.count() == 1 and Movement.objects.count() == 2
                        assert Event.objects.count() == 2 and ActionProposal.objects.count() == 1
                        assert ActionProposal.objects.get(pk=confirmation['proposal_id']).receipt == receipt
                        invariant.balances()
                        probe.report['replays_completed'] = 4
                    with probe.phase('rollback_mark'):
                        transaction.set_rollback(True)
                with probe.phase('counts_after_rollback'):
                    counts_after = table_counts()
                    probe.report['table_counts_after_rollback'] = counts_after
                    assert counts_after == counts_before, 'Unexpected persisted row growth after rollback'
                    probe.report['row_counts_restored_for_one_sequence'] = True
            connection.close()
        probe.report.update(status='complete', one_cycle_complete=True,
                            complete=True, sequences=1, replay_requests=4)
        return 0
    except BaseException as exc:
        # Connection errors can contain secrets; record type, phase and stack only.
        probe.report.update(status='failed', exception_type=type(exc).__name__)
        probe.report['exception_stack'] = [{'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                                          for frame in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps({'diagnostic_failure': type(exc).__name__}), flush=True)
        return 1
    finally:
        faulthandler.cancel_dump_traceback_later()
        if profiler:
            profiler.disable()
            rows = []
            for (filename, line, function), (primitive, calls, own, cumulative, callers) in pstats.Stats(profiler).stats.items():
                rows.append({'file': filename, 'line': line, 'function': function,
                             'primitive_calls': primitive, 'calls': calls,
                             'own_seconds': own, 'cumulative_seconds': cumulative})
            probe.report['profile_top_cumulative'] = sorted(rows, key=lambda row: row['cumulative_seconds'], reverse=True)[:40]
        probe.save()


if __name__ == '__main__':
    raise SystemExit(main())
