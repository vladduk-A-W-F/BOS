"""Bounded CLI protocol and own-child monitor checks; no database/runtime proof."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/maintenance_server.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cli = module('bos_cli_under_test', CLI)


class MaintenanceCLITests(unittest.TestCase):
    def test_strict_ndjson_actions(self):
        for action in ('status', 'resume', 'stop'):
            self.assertEqual(cli.decode_command(json.dumps({'action': action}).encode()), {'action': action})
        self.assertEqual(cli.decode_command(b'{"action":"backup","destination":"/operator/new-backup"}')['action'], 'backup')
        refused = (b'{"action":"activate"}', b'{"action":"status","secret":"CANARY"}',
            b'{"action":"backup"}', b'{"action":"backup","destination":false}',
            b'{"action":"status","action":"stop"}', b'[]', b'null', b'NaN',
            b'{"action":1}', b'\xff', b'{' * 2000, b' ' * (cli.MAX_COMMAND_BYTES + 1))
        for raw in refused:
            with self.subTest(raw_length=len(raw)), self.assertRaises(cli.InputRefused):
                cli.decode_command(raw)

    def test_parser_refusal_is_json_without_input_echo(self):
        cases = (['--CANARY_PASSWORD_DO_NOT_ECHO'], ['activate'],
                 ['serve', '--startup-timeout', 'nan'], ['restore', '--source', '/CANARY_PRIVATE_PATH'])
        for args in cases:
            result = subprocess.run([sys.executable, '-B', str(CLI), *args],
                text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, '')
            event = json.loads(result.stdout)
            self.assertEqual(event['code'], 'INVALID_ARGUMENTS')
            self.assertNotIn('CANARY', result.stdout)

    def test_restore_parser_never_accepts_existing_target_override(self):
        args = ['restore', '--source', '/backup', '--target', '/new', '--registry', '/registry',
                '--wheelhouse', '/wheels', '--origin', 'https://localhost:19443']
        self.assertEqual(cli.parser().parse_args(args).command, 'restore')
        for override in ('--force', '--resume', '--overwrite', '--activate'):
            with self.assertRaises(cli.InputRefused):
                cli.parser().parse_args([*args, override])

    def test_public_metadata_excludes_private_details(self):
        value = cli.public_result({'complete': True, 'scope': 'capture_only',
            'password': 'CANARY_PASSWORD', 'config': {'SECRET_KEY': 'CANARY_SECRET'},
            'worker_stdout': 'CANARY_ROW', 'path': '/CANARY_PRIVATE_PATH'})
        self.assertEqual(value, {'complete': True, 'scope': 'capture_only'})

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux stdin profile')
    def test_actual_pipe_framing_is_bounded_and_preserves_final_line(self):
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, 'rb')
        stopped = threading.Event()
        reader = cli.InputReader(stream, stopped)
        reader.start()
        try:
            os.write(write_fd, b'{"action":')
            with self.assertRaises(queue.Empty):
                reader.events.get(timeout=.05)
            os.write(write_fd, b'"status"}\n{"action":"stop"}\n')
            self.assertEqual(reader.events.get(timeout=2), ('line', b'{"action":"status"}\n'))
            self.assertEqual(reader.events.get(timeout=2), ('line', b'{"action":"stop"}\n'))
            os.write(write_fd, b'x' * cli.MAX_COMMAND_BYTES)
            os.write(write_fd, b'x\n')
            self.assertEqual(reader.events.get(timeout=2), ('invalid', None))
            os.write(write_fd, b'{"action":"status"}')
            os.close(write_fd)
            write_fd = None
            self.assertEqual(reader.events.get(timeout=2), ('line', b'{"action":"status"}'))
            self.assertEqual(reader.events.get(timeout=2), ('eof', None))
        finally:
            reader.close()
            self.assertFalse(reader.thread.is_alive())
            stream.close()
            if write_fd is not None:
                os.close(write_fd)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux stdin profile')
    def test_interpreter_stop_with_parent_stdin_kept_open(self):
        # Actual baseline failed with SIGABRT/_enter_buffered_busy. Parent MUST
        # keep its stdin pipe open until the child exits; EOF is not a fix.
        script = r'''
import importlib.util,json,sys,threading
spec=importlib.util.spec_from_file_location('candidate',sys.argv[1])
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
stopped=threading.Event();reader=candidate.InputReader(sys.stdin.buffer,stopped)
reader.start();print('ready',flush=True)
kind,raw=reader.events.get(timeout=5)
assert kind=='line' and candidate.decode_command(raw)=={'action':'stop'}
threading.Event().wait(.15)
stopped.set();reader.close()
print(json.dumps({'reader_alive':reader.thread.is_alive()}),flush=True)
'''
        child = subprocess.Popen([sys.executable, '-B', '-c', script, str(CLI)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            child.stdin.write('{"action":"stop"}\n')
            child.stdin.flush()
            self.assertEqual(json.loads(child.stdout.readline()), {'reader_alive': False})
            self.assertEqual(child.wait(timeout=7), 0)
            self.assertFalse(child.stdin.closed)
            self.assertEqual(child.stderr.read(), '')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_actual_owned_children_and_logging_failure_monitor(self):
        # This is only the monitor seam. The actual BoSRuntime startup/HTTP and
        # CLI ownership/capture are intentionally left to the integration gate.
        runtime_module = module('bos_runtime_monitor_under_test', ROOT / 'scripts/managed_runtime.py')
        runtime = runtime_module.BoSRuntime(installer=None, target='/unused', registry='/unused',
            installation_id='unused', caddy='/unused', certificate='/unused', private_key='/unused', http_port=19480)
        with self.assertRaises(ValueError):
            runtime.assert_running()
        children = []
        try:
            for _ in range(2):
                child = subprocess.Popen([sys.executable, '-u', '-c',
                    'import sys; print("ready", flush=True); sys.stdin.buffer.read()'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                children.append(child)
                self.assertEqual(child.stdout.readline().strip(), 'ready')
            failed = threading.Event()
            runtime._running = (failed, tuple(children))
            runtime.assert_running()
            failed.set()  # The allowed logging-failure property injection.
            with self.assertRaises(ValueError):
                runtime.assert_running()
            self.assertTrue(all(child.poll() is None for child in children))
            failed.clear()
            children[0].terminate()
            children[0].wait(timeout=3)
            with self.assertRaises(ValueError):
                runtime.assert_running()
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=3)
                for stream in (child.stdin, child.stdout, child.stderr):
                    stream.close()


if __name__ == '__main__':
    unittest.main()
