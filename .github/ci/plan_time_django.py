"""One unchanged F04 test, observed on an explicitly issued PostgreSQL 16 DB.

The parent supervisor owns the 60-second TOTAL process budget and DB cleanup.
No suite/gate acceptance is inferred from this diagnostic. Run with cwd=source.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import wraps
import faulthandler
import inspect
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import traceback
import unittest


TEST_ID = "erp.test_concurrency.ERPProposalConcurrencyTests.test_http_pair_item"
START = time.monotonic()
CPU_START = time.process_time()
LOCAL = threading.local()
LOCK = threading.Lock()
EVENTS = []
SQL_THREADS = []
HASH_CALLS = []
RESULTS = []
PATCHES = []
MISSING = object()
REPORT = {
    "schema": 1,
    "scope": "PLAN-TIME/P06-F04 ONE unchanged Django method, three currency subtests",
    "test_id": TEST_ID,
    "status": "RUNNING",
    "complete": False,
    "root_cause_proven": False,
    "full_suite_run": False,
    "gate_acceptance": False,
    "technical_ready": False,
    "pilot_allowed": False,
    "parent_total_budget_seconds": 60,
    "faulthandler_after_seconds": 45,
    "timing_semantics": "Wall/CPU timings are inclusive and may overlap; CPU is per-thread except total process_cpu_seconds. Do not sum nested phases.",
}


def emit(kind, data):
    print(kind + " " + json.dumps(data, ensure_ascii=False, default=str), flush=True)


@contextmanager
def phase(name, **metadata):
    stack = getattr(LOCAL, "phases", [])
    LOCAL.phases = stack
    started = time.monotonic()
    cpu = time.thread_time()
    row = {
        "name": name,
        "thread_id": threading.get_ident(),
        "thread_name": threading.current_thread().name,
        "parent": stack[-1] if stack else None,
        "started_seconds": started - START,
        **metadata,
    }
    stack.append(name)
    emit("PLAN_TIME_PHASE_START", row)
    try:
        yield
    except BaseException as exc:
        row["exception_type"] = type(exc).__name__
        raise
    finally:
        stack.pop()
        row.update(wall_seconds=time.monotonic() - started,
                   thread_cpu_seconds=time.thread_time() - cpu)
        with LOCK:
            EVENTS.append(row)
        emit("PLAN_TIME_PHASE_END", row)


def patch(owner, name, wrapper_factory):
    """Retain inherited descriptors correctly and restore the exact prior shape."""
    prior = vars(owner).get(name, MISSING)
    descriptor = inspect.getattr_static(owner, name)
    if isinstance(descriptor, classmethod):
        replacement = classmethod(wrapper_factory(descriptor.__func__))
    elif isinstance(descriptor, staticmethod):
        replacement = staticmethod(wrapper_factory(descriptor.__func__))
    else:
        replacement = wrapper_factory(getattr(owner, name))
    setattr(owner, name, replacement)
    PATCHES.append((owner, name, prior))


def observe(name, metadata=None):
    def decorate(original):
        @wraps(original)
        def wrapped(*args, **kwargs):
            extra = metadata(args, kwargs) if metadata else {}
            with phase(name, **extra):
                return original(*args, **kwargs)
        return wrapped
    return decorate


def observe_sql(original):
    @wraps(original)
    def wrapped(*args, **kwargs):
        # SQL strings and parameters are intentionally not collected.
        stats = getattr(LOCAL, "sql", None)
        if stats is None:
            stats = {
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
                "count": 0, "wall_seconds": 0.0, "thread_cpu_seconds": 0.0,
                "errors": 0, "by_phase": {},
            }
            LOCAL.sql = stats
            with LOCK:
                SQL_THREADS.append(stats)
        label = "/".join(getattr(LOCAL, "phases", ())) or "unattributed"
        current = stats["by_phase"].setdefault(label, {
            "count": 0, "wall_seconds": 0.0, "thread_cpu_seconds": 0.0, "errors": 0,
        })
        started, cpu = time.monotonic(), time.thread_time()
        failed = False
        try:
            return original(*args, **kwargs)
        except BaseException:
            failed = True
            raise
        finally:
            elapsed, cpu_elapsed = time.monotonic() - started, time.thread_time() - cpu
            for target in (stats, current):
                target["count"] += 1
                target["wall_seconds"] += elapsed
                target["thread_cpu_seconds"] += cpu_elapsed
                target["errors"] += int(failed)
    return wrapped


def hash_metadata(args, kwargs):
    hasher = args[0]
    iterations = kwargs.get("iterations")
    if iterations is None and len(args) > 3:
        iterations = args[3]
    record = {
        "algorithm": hasher.algorithm,
        "iterations": iterations or hasher.iterations,
    }
    with LOCK:
        HASH_CALLS.append(record)
    return record


class ObservingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_ids = []
        self.completed_ids = []
        self.subtests = []
        self._active_phase = None
        RESULTS.append(self)

    def startTest(self, test):
        self.started_ids.append(test.id())
        self._active_phase = phase("test.result", test_id=test.id())
        self._active_phase.__enter__()
        return super().startTest(test)

    def stopTest(self, test):
        try:
            return super().stopTest(test)
        finally:
            self.completed_ids.append(test.id())
            if self._active_phase:
                self._active_phase.__exit__(None, None, None)
                self._active_phase = None

    def addSubTest(self, test, subtest, err):
        self.subtests.append({"id": subtest.id(), "success": err is None})
        return super().addSubTest(test, subtest, err)


class ObservingTextRunner(unittest.TextTestRunner):
    resultclass = ObservingResult


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def write_report(output):
    report = dict(REPORT)
    report.update(
        wall_seconds=time.monotonic() - START,
        process_cpu_seconds=time.process_time() - CPU_START,
        phases=EVENTS,
        sql_threads=SQL_THREADS,
        password_encode_calls=HASH_CALLS,
        phase_counts={name: sum(row["name"] == name for row in EVENTS)
                      for name in sorted({row["name"] for row in EVENTS})},
    )
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)


def run(output):
    issued = os.environ.get("BOS_TEST_DB_NAME", "")
    if (os.environ.get("BOS_VERIFY_DB") != "postgres"
            or os.environ.get("BOS_PG_DISPOSABLE") != "1"
            or not re.fullmatch(r"bos_verify_[a-f0-9]{16}", issued)
            or os.environ.get("DJANGO_SETTINGS_MODULE") != "verification_settings"):
        raise RuntimeError("Refused: requires an explicitly issued disposable PostgreSQL verification profile")
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE", "") not in ("", "0"):
        raise RuntimeError("Refused: assertions must remain enabled")
    source = Path.cwd().resolve()
    if not (source / "manage.py").is_file() or not (source / "verification_settings.py").is_file():
        raise RuntimeError("Refused: cwd must be the prepared candidate source")
    if not os.environ.get("BOS_TEST_MEDIA"):
        raise RuntimeError("Refused: isolated media path is required")
    expected_test = "test_" + issued
    REPORT["source_root"] = str(source)
    REPORT["issued_database"] = issued
    REPORT["expected_test_database"] = expected_test
    REPORT["media_root"] = os.environ["BOS_TEST_MEDIA"]
    sys.path.insert(0, str(source))

    # Before importing application modules or permitting Django CREATE/DROP DB.
    import psycopg
    with phase("bootstrap.source_database_proof"):
        with psycopg.connect(dbname=issued, host=os.environ["BOS_PGHOST"],
                port=os.environ.get("BOS_PGPORT", "5432"), user=os.environ["BOS_PGUSER"],
                password=os.environ["BOS_PGPASSWORD"], connect_timeout=5, autocommit=True) as source_conn:
            actual, version, version_num = source_conn.execute(
                "SELECT current_database(), current_setting('server_version'), current_setting('server_version_num')").fetchone()
            if actual != issued or not 160000 <= int(version_num) < 170000:
                raise RuntimeError("Refused: issued connection identity or PostgreSQL major version mismatch")
            if source_conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (expected_test,)).fetchone():
                raise RuntimeError("Refused: test database already exists; do not overwrite or reuse it")
            REPORT["source_database_proof"] = {
                "actual_database": actual, "version": version, "version_num": int(version_num),
                "test_database_absent_before_creation": True,
            }

    with phase("bootstrap.django_setup"):
        import django
        django.setup()
        from django.conf import settings
        from django.contrib.auth.hashers import PBKDF2PasswordHasher, get_hasher
        from django.db import connection
        from django.db.backends.utils import CursorWrapper
        from django.test.runner import DiscoverRunner
        from erp import queries, service
        from erp import test_concurrency as fixture
        REPORT["django_version"] = django.get_version()
        hasher = get_hasher()
        REPORT["effective_password_hashers"] = list(settings.PASSWORD_HASHERS)
        REPORT["effective_hasher"] = {
            "algorithm": hasher.algorithm, "iterations": getattr(hasher, "iterations", None),
        }
        if (connection.vendor != "postgresql" or connection.settings_dict["NAME"] != issued
                or connection.creation._get_test_db_name() != expected_test):
            raise RuntimeError("Refused: Django source/test database configuration differs from issued identities")

    patch(CursorWrapper, "execute", observe_sql)
    patch(CursorWrapper, "executemany", observe_sql)
    patch(PBKDF2PasswordHasher, "encode", observe("password.PBKDF2.encode", hash_metadata))
    patch(service, "fingerprint", observe("erp.fingerprint"))
    patch(queries, "snapshot", observe("erp.snapshot"))
    patch(fixture, "business_state", observe("test.business_state"))
    # The fixture imported this function directly; observe that bound reference.
    patch(fixture, "login_test_client", observe("test.actual_http_login"))
    selected = fixture.ERPProposalConcurrencyTests
    for name in ("setUpClass", "tearDownClass", "_pre_setup", "setUp", "test_http_pair_item",
                 "tearDown", "_post_teardown"):
        patch(selected, name, observe("test." + name))
    patch(selected, "run_http_pair", observe("test.currency", lambda args, kw: {
        "action": args[1], "currency": args[2],
    }))
    patch(selected, "http_result", observe("test.confirm_or_replay"))
    patch(selected, "oracle", observe("test.business_oracle"))

    class DiagnosticRunner(DiscoverRunner):
        test_runner = ObservingTextRunner

        def build_suite(self, *args, **kwargs):
            with phase("runner.build_suite"):
                suite = super().build_suite(*args, **kwargs)
                found = [case.id() for case in flatten(suite)]
                REPORT["discovered_test_ids"] = found
                if found != [TEST_ID]:
                    raise RuntimeError("Refused: bounded profile must contain exactly the selected test")
                return suite

        def setup_databases(self, **kwargs):
            with phase("runner.database_setup"):
                old_config = super().setup_databases(**kwargs)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT current_database(), current_setting('server_version_num')")
                        actual_test, version_num = cursor.fetchone()
                    if (connection.vendor != "postgresql" or actual_test != expected_test
                            or connection.settings_dict["NAME"] != expected_test
                            or not 160000 <= int(version_num) < 170000):
                        raise RuntimeError("Refused: actual Django test connection is not the issued PostgreSQL 16 test DB")
                    REPORT["test_database_proof"] = {
                        "actual_database": actual_test, "configured_database": connection.settings_dict["NAME"],
                        "vendor": connection.vendor, "version_num": int(version_num),
                    }
                    REPORT["database"] = {
                        "vendor": "postgresql", "database": actual_test,
                        "version_num": int(version_num),
                    }
                    emit("PLAN_TIME_DATABASE_PROOF", REPORT["test_database_proof"])
                except BaseException:
                    super().teardown_databases(old_config)
                    raise
                return old_config

        def run_checks(self, databases):
            with phase("runner.system_checks"):
                return super().run_checks(databases)

        def teardown_databases(self, old_config, **kwargs):
            with phase("runner.database_teardown"):
                return super().teardown_databases(old_config, **kwargs)

    write_report(output)
    runner = DiagnosticRunner(verbosity=2, interactive=False, keepdb=False,
                              parallel=1, failfast=False, shuffle=False, buffer=False)
    with phase("runner.run_selected_test"):
        failures = runner.run_tests([TEST_ID])
    if len(RESULTS) != 1:
        raise RuntimeError("Expected one observed result")
    result = RESULTS[0]
    REPORT["tests_run"] = result.testsRun
    REPORT["tests_failed"] = len(result.errors) + len(result.failures) + len(result.unexpectedSuccesses)
    REPORT["tests_skipped"] = len(result.skipped)
    REPORT["test_result"] = {
        "tests_run": result.testsRun, "started_ids": result.started_ids,
        "completed_ids": result.completed_ids, "skipped": [(str(t), reason) for t, reason in result.skipped],
        "errors": [(str(t), text) for t, text in result.errors],
        "failures": [(str(t), text) for t, text in result.failures],
        "expected_failures": [(str(t), text) for t, text in result.expectedFailures],
        "unexpected_successes": [str(t) for t in result.unexpectedSuccesses],
        "subtests": result.subtests, "runner_failures": failures,
    }
    good = (failures == 0 and result.wasSuccessful() and result.testsRun == 1
            and result.started_ids == [TEST_ID] and result.completed_ids == [TEST_ID]
            and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
            and len(result.subtests) == 3 and all(s["success"] for s in result.subtests))
    REPORT["status"] = "SCOPED_DIAGNOSTIC_PASS" if good else "SCOPED_DIAGNOSTIC_FAILED"
    return 0 if good else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    faulthandler.enable()
    REPORT['faulthandler_after_seconds'] = min(45, max(.1, float(os.environ.get('BOS_PLAN_TIME_STACK_AFTER', '45'))))
    faulthandler.dump_traceback_later(REPORT['faulthandler_after_seconds'], repeat=False)
    exit_code = 1
    try:
        write_report(output)
        exit_code = run(output)
    except BaseException as exc:
        REPORT["status"] = "SCOPED_DIAGNOSTIC_ERROR"
        REPORT["exception_type"] = type(exc).__name__
        REPORT["traceback"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        faulthandler.cancel_dump_traceback_later()
        for owner, name, prior in reversed(PATCHES):
            if prior is MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, prior)
        REPORT["exit_code"] = exit_code
        REPORT["complete"] = exit_code == 0 and REPORT["status"] == "SCOPED_DIAGNOSTIC_PASS"
        write_report(output)
        emit("PLAN_TIME_RESULT", {"status": REPORT["status"], "exit_code": exit_code,
                                  "root_cause_proven": False, "output": str(output)})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
