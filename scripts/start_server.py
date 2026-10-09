"""BoS loopback-only Waitress with a verified finite drain before exit 0."""
import argparse
from importlib import metadata
import json
import math
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_application(application, *, port, version, runtime_version, drain_timeout=5, emit=None):
    """Own every worker/socket; no graceful acknowledgement while work remains."""
    from waitress import create_server, wasyncore
    from waitress.channel import HTTPChannel
    from waitress.task import ThreadedTaskDispatcher
    if not math.isfinite(drain_timeout) or not 0 < drain_timeout <= 120:
        raise ValueError('Потрібен скінченний строк завершення у межах 120 секунд.')
    emit = emit or (lambda event: print(json.dumps(event), flush=True))

    class OwnedDispatcher(ThreadedTaskDispatcher):
        def __init__(self):
            super().__init__()
            self.owned_threads = []

        def start_new_thread(self, target, thread_no):
            worker = threading.Thread(target=target, name=f'waitress-{thread_no}',
                                      args=(thread_no,), daemon=True)
            self.owned_threads.append(worker)
            worker.start()

    class DrainChannel(HTTPChannel):
        def readable(self):
            # A complete queued request finishes; no new/partial request enters
            # the dispatcher after the listener is closed for drain.
            return not self.server.bos_draining and super().readable()

    dispatcher = OwnedDispatcher()
    dispatcher.set_thread_count(4)
    server = create_server(
        application, host='127.0.0.1', port=port, ipv4=True, ipv6=False,
        _dispatcher=dispatcher, threads=4, ident='BoS', expose_tracebacks=False,
        trusted_proxy=None, trusted_proxy_headers=set(),
        clear_untrusted_proxy_headers=False, log_untrusted_proxy_headers=False,
        log_socket_errors=False, max_request_header_size=16384,
        max_request_body_size=12 * 1024 * 1024, channel_timeout=30,
    )
    server.bos_draining = False
    server.channel_class = DrainChannel
    stopping = threading.Event()
    previous = {kind: signal.getsignal(kind) for kind in (signal.SIGTERM, signal.SIGINT)}
    for kind in previous:
        signal.signal(kind, lambda signum, frame: stopping.set())
    succeeded = False

    def snapshot():
        with dispatcher.lock:
            state = {'queued': len(dispatcher.queue), 'active': dispatcher.active_count,
                     'dispatcher_threads': len(dispatcher.threads)}
        state['live_workers'] = sum(worker.is_alive() for worker in dispatcher.owned_threads)
        state['pending_requests'] = sum(len(channel.requests) for channel in server.active_channels.values())
        state['pending_output_bytes'] = sum(channel.total_outbufs_len for channel in server.active_channels.values())
        return state

    def tick():
        wasyncore.loop(timeout=.025, map=server._map,
                       use_poll=server.adj.asyncore_use_poll, count=1)

    try:
        emit({'event': 'bos.server.bound', 'host': server.effective_host,
              'port': int(server.effective_port), 'version': version,
              'runtime': 'waitress', 'runtime_version': runtime_version})
        while not stopping.is_set():
            tick()
            if not server._map:
                raise RuntimeError('Приватний socket map завершився без запиту зупинки.')
        server.bos_draining = True
        # Base close removes only the listening socket; keep the trigger and
        # existing channels alive so workers can finish and flush responses.
        wasyncore.dispatcher.close(server)
        emit({'event': 'bos.server.draining', 'version': version, **snapshot()})
        deadline = time.monotonic() + drain_timeout
        while time.monotonic() < deadline:
            state = snapshot()
            if not any(state[key] for key in ('queued', 'active', 'pending_requests', 'pending_output_bytes')):
                # Only stop idle workers after all accepted work has finished.
                dispatcher.set_thread_count(0)
                for worker in dispatcher.owned_threads:
                    worker.join(timeout=max(0, deadline - time.monotonic()))
                state = snapshot()
                if not any(state.values()):
                    for channel in list(server.active_channels.values()):
                        if channel.request is not None:
                            channel.request.close()
                        channel.handle_close()
                    server.trigger.close()
                    wasyncore.close_all(server._map)
                    if server._map:
                        raise RuntimeError('Власні сокети не закрито.')
                    succeeded = True
                    emit({'event': 'bos.server.quiescent', 'version': version,
                          'runtime': 'waitress', 'runtime_version': runtime_version,
                          'active': state['active'], 'queued': state['queued'],
                          'workers': state['live_workers'], 'sockets_closed': True})
                    return 0
            tick()
        emit({'event': 'bos.server.drain_failed', 'version': version,
              'reason': 'timeout', **snapshot()})
        return 6
    finally:
        # Failure remains non-graceful. Never use shutdown(cancel_pending=True)
        # as proof and never fabricate a quiescent acknowledgement on timeout.
        if not succeeded:
            dispatcher.set_thread_count(0)
            wasyncore.close_all(server._map)
        for kind, handler in previous.items():
            signal.signal(kind, handler)


def serve(port, drain_timeout):
    # Preserve canonical profile checks before any worker or socket is created.
    from boss_project.server_wsgi import application
    from boss_project.server_config import refuse
    from boss_project.version import VERSION
    try:
        runtime_version = metadata.version('waitress')
    except metadata.PackageNotFoundError:
        refuse('встановлення Waitress 3.0.2 у середовищі інсталяції')
    if runtime_version != '3.0.2':
        refuse('версію Waitress 3.0.2')
    # Connected sources are read in this process only, and the reader ends with the server.
    from connectors import periodic
    periodic.start()
    try:
        return run_application(application, port=port, version=VERSION,
                               runtime_version=runtime_version, drain_timeout=drain_timeout)
    finally:
        periodic.stop()


def main():
    parser = argparse.ArgumentParser(description='Запустити BoS за налаштованим TLS-проксі.')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--drain-timeout', type=float, default=5,
                        help='Скінченний строк завершення активних запитів, секунд (до 120).')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Потрібен порт у межах 0–65535.')
    if not math.isfinite(args.drain_timeout) or not 0 < args.drain_timeout <= 120:
        parser.error('Потрібен скінченний строк завершення у межах 120 секунд.')
    from django.core.exceptions import ImproperlyConfigured
    try:
        return serve(args.port, args.drain_timeout)
    except ImproperlyConfigured as error:
        reason = (str(error) if getattr(error, 'bos_controlled_configuration_error', False)
                  else 'Сервер BoS не запущено: перевірте серверну конфігурацію.')
        print(json.dumps({'event': 'bos.server.refused', 'reason': reason}, ensure_ascii=False), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
