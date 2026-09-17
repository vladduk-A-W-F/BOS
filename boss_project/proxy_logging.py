"""Normalize proxy process output before storage; never retain raw messages.

The caller supplies the version from its validated release manifest. A proxy
correlation ID identifies this normalized event; it is not a request header or
the application's separate request ID. No Django settings or database imports.
"""
import json
import re
import uuid

MAX_LINE_CHARACTERS = 65536
_VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?')


def normalize_proxy_line(line, *, version):
    safe_version = (version if isinstance(version, str) and len(version) <= 64
                    and _VERSION.fullmatch(version) else 'unknown')
    event, status = 'proxy_unstructured', None
    if isinstance(line, str) and len(line) <= MAX_LINE_CHARACTERS:
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            record = None
        if isinstance(record, dict):
            event = 'proxy_log'
            candidate = record.get('status')
            if type(candidate) is int and 100 <= candidate <= 599:
                event, status = 'proxy_request', candidate
    return {'event': event, 'status': status, 'version': safe_version,
            'correlation_id': str(uuid.uuid4())}


def write_proxy_line(line, stream, *, version):
    record = normalize_proxy_line(line, version=version)
    stream.write(json.dumps(record, ensure_ascii=True, separators=(',', ':')) + '\n')
    stream.flush()
