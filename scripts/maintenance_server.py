"""Операторський CLI BoS: same-process serve, offline backup та NEW restore.

stdin control належить лише запущеному цим CLI supervisor. Це не IPC/API
керування іншим процесом. Restore не підтверджує готовність через HTTPS.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
import select
from pathlib import Path
import queue
import signal
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_COMMAND_BYTES = 8192
sys.path.insert(0, str(ROOT))


class InputRefused(ValueError):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's original message can contain arbitrary operator input.
        raise InputRefused('INVALID_ARGUMENTS')


def finite_timeout(value):
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 120:
        raise argparse.ArgumentTypeError('Потрібний timeout від 0 до 120 секунд.')
    return number


def tcp_port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError('Потрібний порт від 1 до 65535.')
    return number


def parser():
    result = SafeParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    restore = commands.add_parser('restore', help='Відновити власний backup лише в новий відсутній target.')
    for name in ('source', 'target', 'registry', 'wheelhouse'):
        restore.add_argument('--' + name, required=True, type=Path)
    restore.add_argument('--origin', required=True)
    for action, explanation in (
        ('backup', 'Власна offline установка: запуск → quiesce → backup → зупинка.'),
        ('serve', 'Власний foreground сервер; SIGINT/SIGTERM завершують фактичний drain.'),
    ):
        command = commands.add_parser(action, help=explanation)
        for name in ('target', 'registry', 'caddy', 'certificate', 'private-key'):
            command.add_argument('--' + name, required=True, type=Path)
        command.add_argument('--installation-id', required=True)
        command.add_argument('--http-port', required=True, type=tcp_port)
        command.add_argument('--ca-certificate', type=Path)
        command.add_argument('--startup-timeout', type=finite_timeout, default=20)
        if action == 'backup':
            command.add_argument('--destination', required=True, type=Path)
        else:
            command.add_argument('--control-stdin', action='store_true',
                help='NDJSON status/backup/resume/stop у цьому процесі; EOF зупиняє сервер.')
    return result


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}, ensure_ascii=False, allow_nan=False), flush=True)


def refused(code, *, command_id=None, state=None):
    event = {'complete': False, 'code': code}
    if command_id is not None:
        event['command_id'] = command_id  # Generated here; never echo input IDs.
    if state is not None:
        event['state'] = state
    emit('bos.maintenance.refused', **event)


def decode_command(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_COMMAND_BYTES:
        raise InputRefused('COMMAND_TOO_LARGE')

    def pairs(items):
        output = {}
        for name, value in items:
            if name in output:
                raise InputRefused('DUPLICATE_FIELD')
            output[name] = value
        return output

    def no_constant(value):
        raise InputRefused('INVALID_JSON_CONSTANT')

    try:
        command = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=no_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise InputRefused('INVALID_COMMAND') from None
    if type(command) is not dict or type(command.get('action')) is not str:
        raise InputRefused('INVALID_COMMAND')
    action = command['action']
    expected = {'action', 'destination'} if action == 'backup' else {'action'}
    if action not in ('status', 'backup', 'resume', 'stop') or set(command) != expected:
        raise InputRefused('UNKNOWN_ACTION_OR_FIELDS')
    if action == 'backup' and (type(command['destination']) is not str or not command['destination']):
        raise InputRefused('INVALID_DESTINATION')
    return command


class InputReader:
    """Bounded Linux stdin polling; no BufferedReader lock survives shutdown."""
    def __init__(self, stream, stopped):
        self.fd, self.stopped = stream.fileno(), stopped
        self.events = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self._read, daemon=False)

    def _send(self, event):
        while not self.stopped.is_set():
            try:
                self.events.put(event, timeout=.2)
                return True
            except queue.Full:
                continue
        return False

    def _read(self):
        pending = b''
        oversized = False
        try:
            while not self.stopped.is_set():
                readable, _, _ = select.select([self.fd], [], [], .2)
                if not readable:
                    continue
                chunk = os.read(self.fd, MAX_COMMAND_BYTES)
                if not chunk:
                    if pending or oversized:
                        self._send(('invalid', None) if oversized else ('line', pending))
                    self._send(('eof', None))
                    return
                parts = chunk.split(b'\n')
                for part in parts[:-1]:
                    if oversized or len(pending) + len(part) + 1 > MAX_COMMAND_BYTES:
                        event = ('invalid', None)
                    else:
                        event = ('line', pending + part + b'\n')
                    if not self._send(event):
                        return
                    pending, oversized = b'', False
                tail = parts[-1]
                if not oversized:
                    if len(pending) + len(tail) > MAX_COMMAND_BYTES:
                        pending, oversized = b'', True
                    else:
                        pending += tail
        except Exception:
            self._send(('input_failed', None))

    def start(self):
        self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise InputRefused('STDIN_READER_NOT_STOPPED')


@contextmanager
def signal_stop():
    stopped = threading.Event()
    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda signum, frame: stopped.set())
        yield stopped
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def public_result(result):
    # Explicit metadata allowlist. Config, paths, worker stdout and secrets are
    # never serialized by this operator command.
    allowed = ('complete', 'scope', 'installation_id', 'source_installation_id',
        'operation_id', 'version', 'manifest_sha256', 'database_sha256',
        'private_files', 'tables', 'elapsed_seconds', 'backup_unchanged',
        'post_restore_http_verified', 'restore_verified', 'identity_policy')
    return {name: result[name] for name in allowed if name in result}


class Session:
    def __init__(self, installer, owner, runtime, args):
        self.installer, self.owner, self.runtime, self.args = installer, owner, runtime, args
        self.lease = None
        self.ledger = None

    def quiesce(self):
        if self.owner.state == 'running':
            self.lease = self.owner.quiesce(str(uuid.uuid4()))
        if self.owner.state != 'quiescent' or self.lease is None:
            raise InputRefused('QUIESCENCE_NOT_CONFIRMED')
        self.lease.assert_live()
        return self.lease

    def backup(self, destination):
        from scripts.generation_ledger import GenerationLedger
        from scripts.backup_server import capture_backup
        # Validate before stopping writers. After quiesce every error leaves
        # the installation stopped until explicit resume/stop in this process.
        destination = self.installer.safe_path(destination)
        if destination.exists():
            raise InputRefused('DESTINATION_MUST_BE_NEW')
        lease = self.quiesce()
        if self.ledger is None:
            path = self.owner.target / 'generations'
            factory = GenerationLedger.open if path.exists() or path.is_symlink() else GenerationLedger.create
            self.ledger = factory(installer=self.installer, target=self.owner.target,
                registry=self.args.registry, installation_id=self.owner.installation_id)
        return capture_backup(ledger=self.ledger, lease=lease, destination=destination)

    def resume(self):
        if self.owner.state != 'quiescent' or self.lease is None:
            raise InputRefused('LIVE_QUIESCENT_LEASE_REQUIRED')
        self.lease.release()
        self.lease = None
        self.runtime.assert_running()

    def status(self):
        facts = self.owner.status()
        if self.owner.state == 'running':
            self.runtime.assert_running()
        return {name: facts[name] for name in ('state', 'installation_id', 'generation', 'operation_id', 'own_children')}


def serve_commands(session, stopped, control_stdin):
    reader = InputReader(sys.stdin.buffer, stopped) if control_stdin else None
    try:
        if reader is not None:
            reader.start()
        return _serve_commands(session, stopped, reader)
    finally:
        if reader is not None:
            reader.close()


def _serve_commands(session, stopped, reader):
    while not stopped.is_set():
        if session.owner.state == 'running':
            session.runtime.assert_running()
        if reader is None:
            stopped.wait(.2)
            continue
        try:
            kind, raw = reader.events.get(timeout=.2)
        except queue.Empty:
            continue
        if kind == 'eof':
            break
        command_id = str(uuid.uuid4())
        if kind == 'input_failed':
            refused('STDIN_READ_FAILED', command_id=command_id, state=session.owner.state)
            session.quiesce()
            return 2
        try:
            if kind == 'invalid':
                raise InputRefused('COMMAND_TOO_LARGE')
            command = decode_command(raw)
            action = command['action']
            if action == 'stop':
                session.quiesce()
                emit('bos.maintenance.stop_requested', command_id=command_id, state='quiescent')
                return 0
            if action == 'status':
                emit('bos.maintenance.status', command_id=command_id, **session.status())
            elif action == 'backup':
                result = session.backup(command['destination'])
                emit('bos.maintenance.backup', command_id=command_id, state='quiescent', **public_result(result))
            elif action == 'resume':
                session.resume()
                emit('bos.maintenance.resumed', command_id=command_id, **session.status())
        except Exception:
            # Keep a valid quiescent lease on capture failure. Neither malformed
            # commands nor failed backup authorize automatic resume.
            refused('COMMAND_REFUSED', command_id=command_id, state=session.owner.state)
            if session.owner.state not in ('running', 'quiescent'):
                return 1
    session.quiesce()
    return 0


def operate(args):
    from scripts import install_server as installer
    if args.command == 'restore':
        from scripts.restore_server import restore_new
        result = restore_new(installer=installer, source=args.source, target=args.target,
            registry=args.registry, origin=args.origin, wheelhouse=args.wheelhouse)
        emit('bos.maintenance.restored', **public_result(result))
        return 0

    from scripts.managed_runtime import BoSRuntime
    from scripts.maintenance_control import ManagedSupervisor
    runtime = BoSRuntime(installer=installer, target=args.target, registry=args.registry,
        installation_id=args.installation_id, caddy=args.caddy, certificate=args.certificate,
        private_key=args.private_key, http_port=args.http_port,
        ca_certificate=args.ca_certificate, startup_timeout=args.startup_timeout,
        emit=lambda event: None)
    result = None
    exit_code = 0
    with signal_stop() as stopped:
        try:
            with ManagedSupervisor(installer=installer, target=args.target, registry=args.registry,
                    installation_id=args.installation_id, start_callback=runtime, drain_timeout=15) as owner:
                owner.start()
                session = Session(installer, owner, runtime, args)
                if stopped.is_set():
                    session.quiesce()
                elif args.command == 'backup':
                    result = session.backup(args.destination)
                else:
                    emit('bos.maintenance.serving', scope='loopback-same-process',
                        control='stdin' if args.control_stdin else 'signals', **session.status())
                    exit_code = serve_commands(session, stopped, args.control_stdin)
        finally:
            stopped.set()  # Reader is explicitly joined before leaving serve_commands.
    if result is not None:
        emit('bos.maintenance.backup', state='closed', source_running=False, **public_result(result))
    emit('bos.maintenance.stopped', complete=exit_code == 0, state='closed')
    return exit_code


def main(argv=None):
    try:
        args = parser().parse_args(argv)
    except (InputRefused, ValueError, OverflowError):
        refused('INVALID_ARGUMENTS')
        return 2
    try:
        return operate(args)
    except KeyboardInterrupt:
        refused('INTERRUPTED')
        return 130
    except Exception:
        refused('OPERATION_REFUSED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
