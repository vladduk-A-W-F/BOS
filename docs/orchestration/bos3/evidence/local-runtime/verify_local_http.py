"""Capture a minimal authenticated local BoS 3.0 HTTP receipt.

This script deliberately makes only read requests plus authentication requests.
It never starts a server, runs Django commands, creates a training session, or
submits an ERP/CRM operation.
"""
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


ACCESS_FILE = Path("D:/3/BOSDev/local-bos3/owner/state/owner-access.json")
COOKIE_FILE = Path("D:/3/BOSDev/local-bos3/owner/state/local-http-cookies.txt")
CASE_IDS = ("BOS3-CASE-01", "BOS3-CASE-02", "BOS3-CASE-03")
EXPECTED_VERSION = "0.3.0-dev.1"
EXPECTED_ORGANIZATION = "ТОВ «МайстерКріплення» · навчальна фабрика"


class ReceiptError(RuntimeError):
    def __init__(self, code, endpoint=None, status=None):
        super().__init__(code)
        self.code = code
        self.endpoint = endpoint
        self.status = status


def fail(code, endpoint=None, status=None):
    raise ReceiptError(code, endpoint, status)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_artifacts(source):
    source = source.resolve()
    if not source.is_dir():
        fail("source_not_directory")
    pdf = source / "docs" / "BoS_3_0_Start_UA.pdf"
    manifest_path = pdf.with_suffix(".manifest.json")
    if not pdf.is_file() or not manifest_path.is_file():
        fail("source_brochure_missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("source_manifest_invalid")
    expected = manifest.get("pdf_sha256") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or manifest.get("version") != EXPECTED_VERSION
            or not isinstance(expected, str) or len(expected) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in expected)):
        fail("source_manifest_contract_invalid")
    actual = sha256(pdf)
    if actual.lower() != expected.lower():
        fail("source_pdf_hash_mismatch")
    return {"pdf": pdf, "pdf_sha256": actual, "manifest": manifest_path}


def access():
    try:
        value = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("owner_access_unavailable")
    if not isinstance(value, dict) or set(value) != {"url", "username", "password"}:
        fail("owner_access_contract_invalid")
    if not all(isinstance(value[key], str) and value[key] for key in value):
        fail("owner_access_contract_invalid")
    try:
        parts = urlsplit(value["url"])
        port = parts.port
    except ValueError:
        fail("owner_access_origin_invalid")
    if (parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "::1")
            or port != 8030 or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        fail("owner_access_origin_invalid")
    return value, "{}://{}".format(parts.scheme, parts.netloc)


def new_client(jar=None):
    handlers = [ProxyHandler({})]
    if jar is not None:
        handlers.append(HTTPCookieProcessor(jar))
    return build_opener(*handlers)


def csrf_token(jar):
    for cookie in jar:
        if cookie.name == "csrftoken":
            return cookie.value
    fail("csrf_cookie_missing", "/api/auth/csrf/")


def request(opener, origin, endpoint, *, method="GET", payload=None, jar=None):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["X-CSRFToken"] = csrf_token(jar)
    target = origin + endpoint
    try:
        with opener.open(Request(target, data=data, headers=headers, method=method), timeout=15) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, b""
    except (URLError, OSError):
        fail("http_unreachable", endpoint)


def expect_status(result, endpoint, expected):
    status = result[0]
    if status != expected:
        fail("unexpected_status", endpoint, status)
    return result


def json_body(result, endpoint):
    try:
        return json.loads(result[2].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        fail("invalid_json", endpoint, result[0])


def require_mapping(value, endpoint, status):
    if not isinstance(value, dict):
        fail("response_shape_invalid", endpoint, status)
    return value


def anonymous_checks(origin):
    client = new_client()
    result = request(client, origin, "/api/training/content/")
    if result[0] not in (401, 403):
        fail("anonymous_training_content_not_denied", "/api/training/content/", result[0])
    result = request(client, origin, "/api/training/brochure.pdf")
    if result[0] not in (401, 403):
        fail("anonymous_brochure_not_denied", "/api/training/brochure.pdf", result[0])
    return {
        "training_content": "denied",
        "brochure": "denied",
    }


def login_client(origin, owner, resume):
    jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
    if resume:
        if not COOKIE_FILE.is_file():
            fail("resume_cookie_jar_missing")
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except (OSError, http.cookiejar.LoadError):
            fail("resume_cookie_jar_invalid")
        client = new_client(jar)
        expect_status(request(client, origin, "/api/auth/me/"), "/api/auth/me/", 200)
        return client, jar, "resumed"

    client = new_client(jar)
    csrf = expect_status(request(client, origin, "/api/auth/csrf/"), "/api/auth/csrf/", 200)
    csrf_payload = require_mapping(json_body(csrf, "/api/auth/csrf/"), "/api/auth/csrf/", 200)
    if csrf_payload.get("training_enabled") is not True:
        fail("training_not_enabled", "/api/auth/csrf/", 200)
    demo = request(client, origin, "/api/auth/demo/", method="POST", payload={"role": "ceo"}, jar=jar)
    expect_status(demo, "/api/auth/demo/", 404)
    login = expect_status(request(client, origin, "/api/auth/login/", method="POST", payload={
        "username": owner["username"], "password": owner["password"]}, jar=jar), "/api/auth/login/", 200)
    principal = require_mapping(json_body(login, "/api/auth/login/"), "/api/auth/login/", 200)
    if principal.get("role") != "ceo":
        fail("owner_role_not_ceo", "/api/auth/login/", 200)
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except OSError:
        fail("cookie_jar_save_failed")
    return client, jar, "logged_in"


def authenticated_checks(client, origin, artifacts):
    status = expect_status(request(client, origin, "/api/operations/status/"), "/api/operations/status/", 200)
    status_payload = require_mapping(json_body(status, "/api/operations/status/"), "/api/operations/status/", 200)
    if (status_payload.get("authenticated") is not True or status_payload.get("role") != "ceo"
            or status_payload.get("training_enabled") is not True):
        fail("operations_status_identity_invalid", "/api/operations/status/", 200)
    organization = status_payload.get("organization")
    if not isinstance(organization, dict) or organization.get("name") != EXPECTED_ORGANIZATION:
        fail("operations_status_organization_invalid", "/api/operations/status/", 200)

    root = expect_status(request(client, origin, "/"), "/", 200)
    if EXPECTED_VERSION.encode("ascii") not in root[2]:
        fail("root_version_missing", "/", 200)
    asset = expect_status(request(client, origin, "/assets/app.js"), "/assets/app.js", 200)
    if not asset[2]:
        fail("app_asset_empty", "/assets/app.js", 200)

    content = expect_status(request(client, origin, "/api/training/content/"), "/api/training/content/", 200)
    catalog = require_mapping(json_body(content, "/api/training/content/"), "/api/training/content/", 200)
    cases = catalog.get("cases")
    if (not isinstance(cases, list) or len(cases) != len(CASE_IDS)
            or not all(isinstance(row, dict) for row in cases)
            or tuple(row.get("case_id") for row in cases) != CASE_IDS):
        fail("training_case_catalog_invalid", "/api/training/content/", 200)
    registry = catalog.get("content")
    areas_checked = False
    if isinstance(registry, dict) and "areas" in registry:
        if not isinstance(registry["areas"], list) or len(registry["areas"]) != 11:
            fail("training_area_catalog_invalid", "/api/training/content/", 200)
        areas_checked = True

    session_states = {}
    for case_id in CASE_IDS:
        endpoint = "/api/training/sessions/{}/".format(case_id)
        state = expect_status(request(client, origin, endpoint), endpoint, 200)
        value = require_mapping(json_body(state, endpoint), endpoint, 200)
        if value.get("available") is not True or value.get("status") not in ("not_started", "available"):
            fail("training_session_not_fresh", endpoint, 200)
        session_states[case_id] = value["status"]

    crm = expect_status(request(client, origin, "/api/crm/"), "/api/crm/", 200)
    crm_payload = require_mapping(json_body(crm, "/api/crm/"), "/api/crm/", 200)
    if crm_payload.get("items") != []:
        fail("crm_index_not_empty", "/api/crm/", 200)

    brochure = expect_status(request(client, origin, "/api/training/brochure.pdf"), "/api/training/brochure.pdf", 200)
    served_pdf = brochure[2]
    if not served_pdf.startswith(b"%PDF-"):
        fail("brochure_not_pdf", "/api/training/brochure.pdf", 200)
    served_hash = hashlib.sha256(served_pdf).hexdigest()
    if served_hash.lower() != artifacts["pdf_sha256"].lower():
        fail("brochure_hash_mismatch", "/api/training/brochure.pdf", 200)

    return {
        "operations_status": "authenticated_ceo_training",
        "root_version": EXPECTED_VERSION,
        "app_js_bytes": len(asset[2]),
        "training_case_ids": list(CASE_IDS),
        "training_areas_checked": areas_checked,
        "training_session_statuses": session_states,
        "crm_items": 0,
        "brochure_pdf_sha256": served_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Capture the owner-local BoS 3.0 HTTP receipt.")
    parser.add_argument("--source", type=Path, required=True,
                        help="Accepted source root containing docs/BoS_3_0_Start_UA.pdf and its manifest.")
    parser.add_argument("--resume", action="store_true",
                        help="Reuse only the private owner-state cookie jar; do not authenticate again.")
    args = parser.parse_args()
    try:
        artifacts = source_artifacts(args.source)
        owner, origin = access()
        result = {
            "scope": "owner_local_http_read_receipt",
            "source_pdf_sha256": artifacts["pdf_sha256"],
            "anonymous": anonymous_checks(origin),
        }
        client, _, auth_mode = login_client(origin, owner, args.resume)
        result["authentication"] = auth_mode
        result.update(authenticated_checks(client, origin, artifacts))
        print(json.dumps({"ok": True, "receipt": result}, ensure_ascii=False, sort_keys=True))
    except ReceiptError as exc:
        error = {"code": exc.code}
        if exc.endpoint is not None:
            error["endpoint"] = exc.endpoint
        if exc.status is not None:
            error["status"] = exc.status
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"ok": False, "error": {"code": "unexpected_local_error"}},
                         ensure_ascii=False, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
