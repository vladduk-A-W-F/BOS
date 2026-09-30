"""Focused in-process checks for the fixed local-demo start-guide endpoint.

This file intentionally imports the view directly.  It does not load a URL
server, open a database, make HTTP requests, or write into the candidate tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def streaming_bytes(response) -> bytes:
    try:
        return b"".join(response.streaming_content)
    finally:
        response.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    sys.path.insert(0, str(root))

    from django.conf import settings

    if not settings.configured:
        settings.configure(
            BASE_DIR=root,
            BOS_DATA_MODE="demo",
            DEFAULT_CHARSET="utf-8",
            SECRET_KEY="start-guide-focused-check",
            USE_I18N=False,
            USE_TZ=True,
        )

    from django.http import Http404
    from django.test import RequestFactory
    from django.test.utils import override_settings
    from boss_project.refinement_views import start_guide

    pdf = root / "docs" / "BoS_v18_Start_UA.pdf"
    urlconf = (root / "boss_project" / "urls.py").read_text(encoding="utf-8")
    require(pdf.is_file(), "Expected fixed start guide PDF in docs/")
    require(
        "path('help/start.pdf', start_guide, name='bos-start-guide')" in urlconf,
        "Expected the fixed /help/start.pdf route only",
    )
    original = pdf.read_bytes()
    original_sha256 = hashlib.sha256(original).hexdigest()
    require(original.startswith(b"%PDF-"), "Start guide is not a PDF payload")
    factory = RequestFactory()
    passed: list[str] = []

    with override_settings(BASE_DIR=root, BOS_DATA_MODE="demo"):
        response = start_guide(factory.get("/help/start.pdf", REMOTE_ADDR="127.0.0.1"))
        require(response.status_code == 200, "Demo loopback guide must return 200")
        require(response["Content-Type"] == "application/pdf", "Guide content type must be application/pdf")
        disposition = response["Content-Disposition"]
        require("attachment" in disposition and "BoS_v18_Start_UA.pdf" in disposition,
                "Guide must be an attachment with the fixed filename")
        require(streaming_bytes(response) == original, "Guide response bytes differ from the fixed PDF")
        passed.append("demo-loopback-attachment-exact-bytes")

    with override_settings(BASE_DIR=root, BOS_DATA_MODE="working"):
        try:
            start_guide(factory.get("/help/start.pdf", REMOTE_ADDR="127.0.0.1"))
        except Http404:
            passed.append("non-demo-404")
        else:
            raise AssertionError("Non-demo guide request must be 404")

    with override_settings(BASE_DIR=root, BOS_DATA_MODE="demo"):
        try:
            start_guide(factory.get("/help/start.pdf", REMOTE_ADDR="198.51.100.11"))
        except Http404:
            passed.append("remote-address-404")
        else:
            raise AssertionError("Non-loopback guide request must be 404")

    with tempfile.TemporaryDirectory(prefix="bos-start-guide-missing-") as missing_root:
        with override_settings(BASE_DIR=Path(missing_root), BOS_DATA_MODE="demo"):
            try:
                start_guide(factory.get("/help/start.pdf", REMOTE_ADDR="127.0.0.1"))
            except Http404:
                passed.append("missing-fixed-file-404")
            else:
                raise AssertionError("Missing fixed guide file must be 404")

    with override_settings(BASE_DIR=root, BOS_DATA_MODE="demo"):
        response = start_guide(factory.post("/help/start.pdf", REMOTE_ADDR="127.0.0.1"))
        try:
            require(response.status_code == 405, "POST guide request must be 405")
            require(response["Allow"] == "GET", "Guide must expose only GET")
        finally:
            response.close()
        passed.append("post-405-get-only")

    require(pdf.read_bytes() == original, "Focused endpoint checks changed the source PDF")
    print(json.dumps({
        "schema": "bos.v18.start-guide-focused.v1",
        "result": "PASS",
        "checks": passed,
        "source_pdf_sha256": original_sha256,
        "scope": "direct Django view only; no database, server, TCP, browser, or product writes",
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
