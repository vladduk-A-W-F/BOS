"""One-HTTP post-start verifier for the future immutable D/dev8 delivery.

This template is not executable while the paired delivery template has PENDING
pins. It does not start, stop, write, migrate, seed, reset, retry, or perform
any application check other than the one exact loopback HTTP request.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import maintenance_dev8_d_delivery_template as delivery


class VerificationError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalized_newlines(value):
    return value.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_attestation(path, layout, source, digest, protected_digest, pins, candidate_blobs):
    path = path.resolve()
    try:
        path.relative_to(layout["state"])
    except ValueError as error:
        raise VerificationError("Capture attestation must remain below instance state.") from error
    if not delivery.ARCHIVE_NAME.fullmatch(path.parent.name):
        raise VerificationError("Capture attestation is outside a delivery archive.")
    attestation = delivery.read_json(path)
    expected = {
        "schema": "bos3.invoice-dev8-d.started-attestation/v1", "card": delivery.CARD_ID,
        "from_source": str(delivery.FROM_C_SOURCE.resolve()), "from_commit": delivery.FROM_C_COMMIT,
        "to_source": str(source), "to_commit": delivery.DEV8_COMMIT, "to_source_sha256": digest,
        "version": delivery.DEV8_VERSION, "manifest_path": delivery.DEV8_MANIFEST_PATH,
        "manifest_sha256": pins["manifest_sha256"], "allowlist_sha256": pins["allowlist_sha256"],
        "final_review_sha256": pins["final_review_sha256"], "root_technical_go": pins["root_technical_go"],
    }
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise VerificationError("Capture attestation does not bind the D/dev8 delivery.")
    if attestation.get("verified_candidate_blobs") != candidate_blobs:
        raise VerificationError("Capture attestation lacks the exact final dev8 blob proof.")
    if attestation.get("protected_payload_sha256") != protected_digest:
        raise VerificationError("Protected payload differs from fresh capture attestation.")
    return attestation


def require_prepared(layout, source, digest):
    prepared = delivery.read_json(layout["prepared"])
    expected_database = layout["data"] / "bos3-fasteners.sqlite3"
    if (prepared.get("source") != str(source) or prepared.get("source_sha256") != digest
            or prepared.get("database") != str(expected_database) or prepared.get("port") != delivery.RUNTIME_PORT
            or not prepared.get("initialized_at") or not expected_database.is_file()):
        raise VerificationError("Prepared metadata does not bind the served D/dev8 source.")
    return prepared


def one_exact_loopback_get(port):
    url = "http://127.0.0.1:" + str(port) + "/"
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers={"Accept": "text/html"})
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 200 or response.geturl() != url:
                raise VerificationError("Loopback response was not a direct HTTP 200.")
            return url, response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as error:
        raise VerificationError("One bounded loopback GET failed.") from error


def verify(args):
    delivery.require_final_pins()
    source, root = args.to_source.resolve(), args.root.resolve()
    delivery.require_fixed_paths(delivery.FROM_C_SOURCE.resolve(), source, root)
    layout = delivery.paths(root)
    pins, digest, _, candidate_blobs = delivery.require_d_target(source)
    prepared = require_prepared(layout, source, digest)
    protected_digest = delivery.protected_payload_digest(layout)
    attestation = require_attestation(args.attestation, layout, source, digest, protected_digest, pins, candidate_blobs)
    receipt = delivery.require_ready_receipt(layout, source, digest)
    template = (source / "frontend" / "boss_app_html.html").read_text(encoding="utf-8")
    if template.count("{{ bos_version }}") != 1:
        raise VerificationError("Committed D/dev8 HTML does not contain exactly one version token.")
    expected_html = normalized_newlines(template.replace("{{ bos_version }}", delivery.DEV8_VERSION))
    url, served_html = one_exact_loopback_get(prepared["port"])
    if normalized_newlines(served_html) != expected_html:
        raise VerificationError("One HTTP response differs from the exact immutable D/dev8 template.")
    print(json.dumps({
        "schema": "bos3.invoice-dev8-d.post-start-proof/v1", "url": url, "http_status": 200,
        "served_version": delivery.DEV8_VERSION, "source_commit": delivery.DEV8_COMMIT,
        "source_sha256": digest, "manifest_path": delivery.DEV8_MANIFEST_PATH,
        "manifest_sha256": pins["manifest_sha256"], "prepared_source_sha256": prepared["source_sha256"],
        "verified_candidate_blobs": candidate_blobs,
        "process_identity": receipt["process"], "protected_payload_sha256": protected_digest,
        "protected_payload_matches_capture": True, "capture_at": attestation.get("at"),
        "expected_html_sha256": sha256_text(expected_html), "served_html_sha256": sha256_text(normalized_newlines(served_html)),
        "writes_performed": False, "http_requests": 1, "retries_performed": 0,
    }, sort_keys=True))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--to-source", type=Path, required=True)
    result.add_argument("--root", type=Path, required=True)
    result.add_argument("--attestation", type=Path, required=True)
    return result


if __name__ == "__main__":
    try:
        verify(parser().parse_args())
    except (delivery.DeliveryError, OSError, VerificationError) as error:
        print("BOS3_DEV8_D_POST_START_REFUSED: " + str(error), file=sys.stderr)
        raise SystemExit(2)
