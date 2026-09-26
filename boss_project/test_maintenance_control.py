"""Real same-process maintenance control regression tests (Linux, Waitress 3.0.2).

Each test owns a NEW synthetic bundle, registry and SQLite databases. The bundle
record supplies the controller's admission precondition; it deliberately does
not claim dependency provisioning, a migrated BoS schema, TLS, backup or restore.
The production controller and drain runner are imported only canonically.
Actual HTTP, Popen handles, kernel flock and completed SQLite writes are the
oracles. Missing code or runtime is a failure, never an optional skip.
"""
import fcntl
import hashlib
import http.client
from importlib import metadata
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

from scripts import install_server as installer
from scripts import maintenance_control as control


SOURCE = Path(control.__file__).resolve().parents[1]
WORKER = Path(__file__).resolve().parents[1] / 'fixtures/synthetic/maintenance_wsgi.py'


def http_request(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, response.read().decode('utf-8')
    finally:
        connection.close()


class HeldRuntime:
    """Trusted local test callback: own real child, stdout receipt and HTTP health."""
    def __init__(self, work, *, drain_timeout=3):
        self.work = work
        self.drain_timeout = drain_timeout
        self.events = queue.Queue()
        self.observed = []
        self.generations = []
        self.processes = []
        self.readers = []
        self.reader_errors = []
        self.stderr = []

    def __call__(self, owner):
        work = self.work / ('generation-' + str(len(self.generations)))
        work.mkdir(mode=0o700)
        # Keep the actual product import rooted in the tested checkout/package.
        # The current interpreter supplies the already pinned test environment.
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        inherited_paths = [str(Path(path)) for path in sys.path if path]
        environment['PYTHONPATH'] = os.pathsep.join([str(SOURCE), *inherited_paths])
        process = owner.spawn('waitress', [sys.executable, '-B', str(WORKER),
            '--work', str(work), '--timeout', str(self.drain_timeout)], cwd=SOURCE,
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        self.processes.append(process)
        bound_events = queue.Queue()

        def stdout_reader():
            try:
                for line in process.stdout:
                    event = json.loads(line)
                    self.observed.append(event)
                    self.events.put(event)
                    if event['event'] == 'bos.server.bound':
                        bound_events.put(event)
                    elif event['event'] == 'bos.server.quiescent':
                        owner.record_drain(process, event)
            except BaseException as error:
                self.reader_errors.append(repr(error))

        def stderr_reader():
            try:
                for line in process.stderr:
                    self.stderr.append(line)
            except BaseException as error:
                self.reader_errors.append(repr(error))

        for callback, stream in ((stdout_reader, process.stdout), (stderr_reader, process.stderr)):
            thread = threading.Thread(target=callback, daemon=True)
            self.readers.append(thread)
            owner.track_reader(thread, streams=(stream,))
            thread.start()
        try:
            bound = bound_events.get(timeout=10)
        except queue.Empty as error:
            raise AssertionError('No actual child bound event: ' + ''.join(self.stderr)) from error
        if (bound.get('runtime_version') != '3.0.2' or bound.get('host') != '127.0.0.1'
                or bound.get('runtime') != 'waitress' or type(bound.get('port')) is not int):
            raise AssertionError('Unverified fixture runtime: ' + repr(bound))
        if http_request(bound['port'], '/health') != (200, 'synthetic-waitress-ready'):
            raise AssertionError('The owned Waitress fixture did not answer HTTP health')
        self.generations.append({'work': work, 'port': bound['port'], 'process': process})

    @property
    def current(self):
        return self.generations[-1]

    def wait_event(self, name, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if event.get('event') == name:
                return event
        raise AssertionError('No actual child event: ' + name)

    def unblock_requests(self):
        for work in self.work.glob('generation-*'):
            (work / 'release').touch()


class MaintenanceControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux' or not Path('/proc/self/fdinfo').is_dir():
            raise AssertionError('These ownership tests require the Linux flock receipt profile')
        if metadata.version('waitress') != '3.0.2':
            raise AssertionError('These real subprocess tests require Waitress 3.0.2')
        if not WORKER.is_file():
            raise AssertionError('The canonical synthetic WSGI fixture is missing')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bos-maintenance-control-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.target = self.work / 'company'
        self.registry = self.work / 'registry'
        bootstrap = installer.prepare_install(target=self.target, registry=self.registry,
            source_root=SOURCE, origin='https://bos.example.test')
        self.assertFalse(bootstrap['complete'])
        self.installation_id = bootstrap['installation_id']
        self.database = self.target / 'state/data/bos.sqlite3'
        installer.new_file(self.database, b'')
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            connection.execute('INSERT INTO sentinel VALUES (1, ?)', ('untouched admission fixture',))
        logs = self.target / 'runtime-logs'
        logs.mkdir(mode=0o700)
        registry = installer.InstallerRegistry(self.registry)
        with registry.lock():
            record = registry.get(self.installation_id)
            # Explicit unit-fixture precondition, not an installer completion
            # result. Every owned inode is real; no issued capability is forged.
            record['runtime'] = {'application_provisioned': True,
                'owned_trees': {'runtime-logs': installer.identity(logs)},
                'database': installer.identity(self.database)}
            registry.update(record)
        self.database_before = self.database.read_bytes()
        self.config_before = {name: (self.target / name).read_bytes()
                              for name in ('config/server.json', 'INSTALLATION.json')}
        self.runtimes = []
        self.owners = []
        self.threads = []
        self.addCleanup(self.cleanup_owned_fixture)

    def cleanup_owned_fixture(self):
        # Always release only our synthetic held writers before cleanup, even
        # after a failed assertion; never signal a process from a persisted PID.
        for runtime in self.runtimes:
            runtime.unblock_requests()
        for owner in reversed(self.owners):
            owner.close()
        for thread in self.threads:
            thread.join(timeout=12)
        self.assertTrue(all(not thread.is_alive() for thread in self.threads), 'Test worker leaked')
        for runtime in self.runtimes:
            self.assertTrue(all(child.poll() is not None for child in runtime.processes), 'Own child leaked')
            self.assertTrue(all(not reader.is_alive() for reader in runtime.readers), 'Own reader leaked')
            self.assertEqual(runtime.reader_errors, [])
        self.assertEqual(self.database.read_bytes(), self.database_before, 'Admission database changed')
        self.assertEqual({name: (self.target / name).read_bytes() for name in self.config_before}, self.config_before)

    def runtime(self, *, drain_timeout=3):
        work = self.work / ('runtime-' + str(len(self.runtimes)))
        work.mkdir(mode=0o700)
        runtime = HeldRuntime(work, drain_timeout=drain_timeout)
        self.runtimes.append(runtime)
        return runtime

    def owner(self, runtime, *, enter=True):
        owner = control.ManagedSupervisor(installer=installer, target=self.target,
            registry=self.registry, installation_id=self.installation_id,
            start_callback=runtime, drain_timeout=5)
        self.owners.append(owner)
        if enter:
            owner.__enter__()
        return owner

    def running(self, *, drain_timeout=3):
        runtime = self.runtime(drain_timeout=drain_timeout)
        owner = self.owner(runtime)
        self.assertEqual(owner.start()['state'], 'running')
        return owner, runtime

    def paused(self):
        owner, runtime = self.running()
        operation = str(uuid.uuid4())
        lease = owner.quiesce(operation)
        self.assertIs(type(lease), control.QuiescenceLease)
        self.assertIs(lease.assert_live(), lease)
        self.assertEqual(owner.status()['own_children'], 0)
        self.assertEqual(owner.status()['stopped'], [{'runtime': 'waitress', 'exit_code': 0, 'forced': False}])
        return owner, runtime, operation, lease

    def background(self, callback):
        result = {}
        started = threading.Event()
        finished = threading.Event()

        def invoke():
            started.set()
            try:
                result['value'] = callback()
            except BaseException as error:
                result['error'] = error
            finally:
                finished.set()
        thread = threading.Thread(target=invoke, daemon=True)
        self.threads.append(thread)
        thread.start()
        self.assertTrue(started.wait(timeout=2))
        return thread, finished, result

    def joined(self, task):
        thread, finished, result = task
        self.assertTrue(finished.wait(timeout=12), 'Background operation did not finish')
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        if 'error' in result:
            raise result['error']
        return result.get('value')

    def wait_file(self, path):
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(path.is_file(), str(path))

    def rows(self, runtime):
        with sqlite3.connect(runtime.current['work'] / 'ledger.sqlite3') as connection:
            return connection.execute('SELECT id, value FROM writes ORDER BY id').fetchall()

    def test_instance_flock_and_unissued_capability_refuse_second_owner(self):
        owner, runtime = self.running()
        other = self.owner(runtime, enter=False)
        with self.assertRaises(BlockingIOError):
            other.__enter__()
        with self.assertRaises(control.ControlRefused):
            control.QuiescenceLease(object(), owner, str(uuid.uuid4()))
        with self.assertRaises(control.ControlRefused):
            owner.record_drain(object(), {'event': 'bos.server.quiescent'})
        self.assertEqual(owner.status()['state'], 'running')
        self.assertIsNone(runtime.current['process'].poll())
        self.assertEqual(len(runtime.processes), 1)

    def test_held_http_write_and_response_complete_before_quiescent_lease(self):
        owner, runtime = self.running()
        active = runtime.current
        http = self.background(lambda: http_request(active['port'], '/1'))
        self.wait_file(active['work'] / 'entered-1')
        pause = self.background(lambda: owner.quiesce(str(uuid.uuid4())))
        draining = runtime.wait_event('bos.server.draining')
        self.assertGreaterEqual(draining['active'], 1)
        self.assertFalse(pause[1].wait(timeout=.1), 'Lease issued while a writer was held')
        self.assertNotIn('value', pause[2])
        self.assertEqual(self.rows(runtime), [])
        self.assertFalse((active['work'] / 'committed-1').exists())
        (active['work'] / 'release').touch()
        lease = self.joined(pause)
        self.assertEqual(self.joined(http), (200, 'completed:1'))
        self.assertEqual(self.rows(runtime), [('1', 'committed')])
        self.assertIs(lease.assert_live(), lease)
        self.assertEqual(active['process'].poll(), 0)
        receipt = runtime.wait_event('bos.server.quiescent')
        self.assertEqual({key: receipt[key] for key in ('active', 'queued', 'workers', 'sockets_closed')},
                         {'active': 0, 'queued': 0, 'workers': 0, 'sockets_closed': True})
        self.assertEqual(owner.status()['own_children'], 0)

    def test_live_capture_callback_reads_unchanged_database_under_fence(self):
        owner, runtime, operation, lease = self.paused()

        def capture_callback(capability):
            self.assertIs(capability.assert_for(self.installation_id, self.target, operation), lease)
            self.assertEqual(owner.status()['state'], 'quiescent')
            self.assertTrue(all(child.poll() == 0 for child in runtime.processes))
            return hashlib.sha256(self.database.read_bytes()).hexdigest()

        with lease.fenced_for(self.installation_id, self.target, operation) as capability:
            self.assertEqual(capture_callback(capability), hashlib.sha256(self.database_before).hexdigest())
        self.assertIs(lease.assert_live(), lease)

    def test_lease_bindings_refuse_other_installation_root_operation_and_mutation(self):
        owner, runtime, operation, lease = self.paused()
        for installation_id, root, operation_id in (
                (str(uuid.uuid4()), self.target, operation),
                (self.installation_id, self.work, operation),
                (self.installation_id, self.target, str(uuid.uuid4()))):
            with self.subTest(root=root, operation_id=operation_id), self.assertRaises(control.ControlRefused):
                lease.assert_for(installation_id, root, operation_id)
        for name, value in (('installation_id', str(uuid.uuid4())), ('root', self.work),
                            ('root_identity', (0, 0)), ('operation_id', str(uuid.uuid4()))):
            with self.subTest(field=name), self.assertRaises(AttributeError):
                setattr(lease, name, value)
        self.assertIs(lease.assert_live(), lease)

    def test_active_generation_refuses_same_generation_resume_and_fresh_start(self):
        owner, runtime, operation, lease = self.paused()
        generations = self.target / 'generations'
        generations.mkdir(mode=0o700)
        installer.new_file(generations / 'ACTIVE.json', b'{"synthetic":"another generation"}\n')
        with self.assertRaises(control.ControlRefused):
            lease.release()
        self.assertIs(lease.assert_live(), lease)
        self.assertEqual(owner.status()['state'], 'quiescent')
        self.assertEqual(len(runtime.processes), 1)
        owner.close()
        another_runtime = self.runtime()
        another_owner = self.owner(another_runtime, enter=False)
        with self.assertRaises(control.ControlRefused):
            another_owner.__enter__()
        self.assertEqual(another_runtime.processes, [])

    def test_capture_fence_blocks_release_then_real_resume_revokes_old_lease(self):
        owner, runtime, operation, lease = self.paused()
        with lease.fenced_for(self.installation_id, self.target, operation):
            resume = self.background(lease.release)
            self.assertFalse(resume[1].wait(timeout=.1), 'Resume crossed the active capture fence')
            self.assertEqual(len(runtime.processes), 1)
            self.assertEqual(owner.status()['state'], 'quiescent')
        self.assertEqual(self.joined(resume)['state'], 'running')
        self.assertEqual(len(runtime.generations), 2)
        self.assertIsNot(runtime.generations[0]['process'], runtime.generations[1]['process'])
        self.assertEqual(runtime.generations[0]['process'].poll(), 0)
        self.assertIsNone(runtime.generations[1]['process'].poll())
        with self.assertRaises(control.ControlRefused):
            lease.assert_live()
        with self.assertRaises(control.ControlRefused):
            lease.release()

    def test_external_kernel_unlock_invalidates_lease_without_relocking(self):
        owner, runtime, operation, lease = self.paused()
        # Deliberately release the real fd lock; matching paths/inodes alone
        # must not be accepted as a still-live ownership fence.
        fcntl.flock(owner._lock_file.fileno(), fcntl.LOCK_UN)
        with self.assertRaises(control.ControlRefused):
            lease.assert_live()
        second = self.owner(self.runtime())
        self.assertEqual(second.status()['state'], 'idle')
        with self.assertRaises(control.ControlRefused):
            lease.assert_live()
        second.close()

    def test_closed_owner_invalidates_lease_and_leaves_unrelated_owned_child_alive(self):
        unrelated = subprocess.Popen([sys.executable, '-B', '-c',
            'import sys,time; print("ready",flush=True); time.sleep(30)'], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(self.joined(self.background(unrelated.stdout.readline)).strip(), 'ready')
            owner, runtime, operation, lease = self.paused()
            owner.close()
            with self.assertRaises(control.ControlRefused):
                lease.assert_live()
            with self.assertRaises(control.ControlRefused):
                lease.release()
            self.assertTrue(all(child.poll() == 0 for child in runtime.processes))
            self.assertIsNone(unrelated.poll(), 'Controller stopped an unrelated process')
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)
            unrelated.stdout.close()

    def test_real_drain_timeout_refuses_lease_and_has_no_post_exit_write(self):
        owner, runtime = self.running(drain_timeout=.3)
        active = runtime.current
        http = self.background(lambda: http_request(active['port'], '/7'))
        self.wait_file(active['work'] / 'entered-7')
        with self.assertRaises(control.ControlRefused):
            owner.quiesce(str(uuid.uuid4()))
        self.assertEqual(owner.status()['state'], 'failed')
        self.assertEqual(owner.status()['stopped'], [{'runtime': 'waitress', 'exit_code': 6, 'forced': False}])
        self.assertEqual(active['process'].poll(), 6)
        self.assertTrue(http[1].wait(timeout=5), 'HTTP did not close after child exit')
        self.assertIn('error', http[2])
        self.assertNotIn('value', http[2])
        self.assertFalse(any(event['event'] == 'bos.server.quiescent' for event in runtime.observed))
        failure = runtime.wait_event('bos.server.drain_failed')
        self.assertEqual(failure['reason'], 'timeout')
        self.assertGreaterEqual(failure['active'], 1)
        self.assertEqual(self.rows(runtime), [])
        # Even making release available AFTER confirmed child exit cannot
        # produce a late commit from a stranded daemon writer.
        (active['work'] / 'release').touch()
        time.sleep(.05)
        self.assertEqual(self.rows(runtime), [])
        self.assertFalse((active['work'] / 'committed-7').exists())

    def test_same_generation_cycle_preserves_data_and_closes_every_owned_child(self):
        owner, runtime, operation, lease = self.paused()
        self.assertEqual(lease.release()['generation'], 2)
        second = owner.quiesce(str(uuid.uuid4()))
        with self.assertRaises(control.ControlRefused):
            lease.assert_live()
        self.assertIs(second.assert_live(), second)
        self.assertNotEqual(second.operation_id, operation)
        self.assertEqual(self.database.read_bytes(), self.database_before)
        self.assertTrue(all(child.poll() == 0 for child in runtime.processes))
        self.assertEqual(owner.status()['own_children'], 0)
        self.assertEqual(len(runtime.generations), 2)
        owner.close()
        with self.assertRaises(control.ControlRefused):
            second.assert_live()


if __name__ == '__main__':
    unittest.main(verbosity=2)
