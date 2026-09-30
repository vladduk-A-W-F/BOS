"""Receipt-only verifier for one already-started BoS dev7 owner-local update.

This module does not start, stop, write, migrate, seed, reset, retry, or open
a browser. It performs one no-cookie, no-proxy, no-redirect loopback GET only
after the reviewed delivery runner has started the instance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import maintenance_dev7_delivery as delivery


LOOPBACK_URL = 'http://127.0.0.1:8030/'
SERVED_VERSION = '0.3.0-dev.7'
ATTESTATION_KIND = 'bos3.uxd02-delivery.started-attestation.v1'


class VerificationError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalized_newlines(value):
    """Django/template transports may differ only in CRLF versus LF representation."""
    return value.replace('\r\n', '\n').replace('\r', '\n')


def sha256_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def require_attestation(attestation_path, layout, source, approved_sha, manifest, protected_hash):
    path = attestation_path.resolve()
    try:
        path.relative_to(layout['state'])
    except ValueError as exc:
        raise VerificationError('Fresh capture attestation must reside below protected instance state.') from exc
    if not delivery.ARCHIVE_NAME.fullmatch(path.parent.name):
        raise VerificationError('Fresh capture attestation is outside a one-shot delivery archive.')
    attestation = delivery.read_json(path)
    expected = {
        'schema': 1,
        'kind': ATTESTATION_KIND,
        'old_sha': delivery.BASELINE_SHA,
        'new_sha': approved_sha,
        'manifest_path': manifest['path'],
        'manifest_sha256': manifest['sha256'],
        'source': str(source),
        'root': str(layout['root']),
    }
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise VerificationError('Fresh capture attestation does not bind this delivery.')
    if not isinstance(attestation.get('process_identity'), dict):
        raise VerificationError('Fresh capture attestation lacks process identity.')
    for field in ('source_sha256', 'prepared_sha256'):
        if not isinstance(attestation.get(field), str) or not re.fullmatch(r'[0-9a-f]{64}', attestation[field]):
            raise VerificationError(f'Fresh capture attestation lacks valid {field}.')
    if attestation.get('protected_payload_sha256') != protected_hash:
        raise VerificationError('Protected payload differs from fresh capture attestation.')
    return attestation


def require_prepared_dev7(layout, source, digest):
    prepared = delivery.read_json(layout['prepared'])
    expected_database = layout['data'] / 'bos3-fasteners.sqlite3'
    if (prepared.get('source') != str(source)
            or prepared.get('source_sha256') != digest
            or prepared.get('database') != str(expected_database)
            or prepared.get('port') != 8030
            or not prepared.get('initialized_at')
            or not expected_database.is_file()):
        raise VerificationError('Prepared receipt does not bind the served dev7 source.')
    return prepared


def get_served_html():
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(LOOPBACK_URL, headers={'Accept': 'text/html'})
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 200 or response.geturl() != LOOPBACK_URL:
                raise VerificationError('Loopback response was not a direct HTTP 200.')
            return response.read().decode('utf-8')
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise VerificationError('Bounded loopback GET failed.') from exc


def verify(args):
    source = args.source.resolve()
    root = args.root.resolve()
    layout = delivery.paths(root)
    if delivery.git(source, 'rev-parse', 'HEAD').stdout.strip() != delivery.APPROVED_CANDIDATE_SHA:
        raise VerificationError('Runtime source does not equal the reviewed dev7 candidate.')
    approved_sha, manifest = delivery.require_approved_candidate(source, delivery.BASELINE_SHA)
    if approved_sha != delivery.APPROVED_CANDIDATE_SHA:
        raise VerificationError('Reviewed candidate pin changed during verification.')
    digest = delivery.source_digest(source)
    prepared = require_prepared_dev7(layout, source, digest)
    protected_hash = delivery.protected_payload_digest(layout)
    attestation = require_attestation(args.attestation, layout, source, approved_sha, manifest, protected_hash)
    receipt = delivery.verify_ready_receipt(layout, source, prepared)
    expected_template = (source / 'frontend' / 'boss_app_html.html').read_text(encoding='utf-8')
    if expected_template.count('{{ bos_version }}') != 1:
        raise VerificationError('Committed HTML does not contain exactly one version token.')
    expected_html = normalized_newlines(expected_template.replace('{{ bos_version }}', SERVED_VERSION))
    served_html = normalized_newlines(get_served_html())
    if served_html != expected_html:
        raise VerificationError('Served HTML differs from the committed dev7 template.')
    proof = {
        'schema': 1,
        'kind': 'bos3.uxd02-delivery.post-start-proof.v1',
        'url': LOOPBACK_URL,
        'http_status': 200,
        'served_version': SERVED_VERSION,
        'source_commit': approved_sha,
        'source_sha256': digest,
        'manifest_path': manifest['path'],
        'manifest_sha256': manifest['sha256'],
        'prepared_source_sha256': prepared['source_sha256'],
        'process_identity': receipt['process'],
        'protected_payload_sha256': protected_hash,
        'protected_payload_matches_fresh_attestation': True,
        'expected_html_sha256': sha256_text(expected_html),
        'served_html_sha256': sha256_text(served_html),
        'newline_comparison': 'CRLF and LF normalized before exact text comparison',
        'writes_performed': False,
        'retries_performed': 0,
    }
    print(json.dumps(proof, ensure_ascii=False, sort_keys=True))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--source', type=Path, required=True)
    result.add_argument('--root', type=Path, required=True)
    result.add_argument('--attestation', type=Path, required=True)
    return result


if __name__ == '__main__':
    try:
        verify(parser().parse_args())
    except (delivery.DeliveryError, OSError, VerificationError) as error:
        print('BOS3_POST_START_DEV7_REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
