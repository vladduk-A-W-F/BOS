"""Periodic reading of connected sources inside the running BoS process (M3 §7).

One reader per server process: the entry points start it after Django is ready, and it ends with the
process. It reads only what «Оновити» would read — healthy linked sources (published Google Sheets and links
to other servers) last read more than
STALE_AFTER ago — through the same sync_connector, so a disable, an error or a newer manual read always
wins, and a source in error keeps its last successful time until a person refreshes it. Uploaded files
are never re-read. No external scheduler, queue or separate timer process; nothing is written to sources.
"""
import logging
import threading

from django.db import close_old_connections, connection

LOG = logging.getLogger('bos.connectors')
INTERVAL = 60   # seconds between checks; a source itself is read at most once per STALE_AFTER

_guard = threading.Lock()
_reader = None


def run_once(now=None):
    """Read every due source once: {'synced': [ids], 'failed': [{'id', 'error'}]}."""
    from . import sources
    from .models import Connector
    from .views import stale_sheets, sync_connector
    result = {'synced': [], 'failed': []}
    for connector in stale_sheets(Connector.objects.all(), now):
        try:
            sync_connector(connector)
            result['synced'].append(connector.pk)
        except sources.SourceError as exc:
            result['failed'].append({'id': connector.pk, 'error': str(exc)})
    return result


class Reader:
    """A daemon thread that checks for due sources every `interval` seconds until stopped."""

    def __init__(self, interval=INTERVAL):
        self.interval = interval
        self.stopping = threading.Event()
        self.cycles = 0
        self.last = None
        self.thread = threading.Thread(target=self._loop, name='bos-connectors', daemon=True)

    def _loop(self):
        # The first check comes one interval after start: starting the server never touches the database
        # by itself, and a stop request is honoured at once between checks.
        while not self.stopping.wait(self.interval):
            try:
                close_old_connections()
                self.last = run_once()
            except Exception:   # a broken cycle must not end reading for the life of the process
                LOG.exception('Періодичне читання підключених джерел не вдалося')
            finally:
                # This thread's own connection: never keep a database handle between checks.
                connection.close()
            self.cycles += 1

    def stop(self, timeout=10):
        """Ask the reader to finish; True when it has (a read in progress may take up to its fetch timeout)."""
        self.stopping.set()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout)
        return not self.thread.is_alive()


def start(interval=INTERVAL):
    """Start this process's reader once; a second call returns the running one."""
    global _reader
    with _guard:
        if _reader is None or not _reader.thread.is_alive():
            _reader = Reader(interval)
            _reader.thread.start()
        return _reader


def stop(timeout=10):
    """Stop this process's reader, if any; True when nothing is left running."""
    global _reader
    with _guard:
        reader, _reader = _reader, None
    return reader.stop(timeout) if reader else True
