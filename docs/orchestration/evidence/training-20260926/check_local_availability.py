"""One-pass availability observation for the refreshed local v18 preview.

It permits exactly four GETs to the fixed loopback origin.  It has no retry,
authentication, database, browser, or product-write behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen


EXPECTED_ORIGIN = "http://127.0.0.1:8018/"
EXPECTED_VERSION = "0.2.18-current"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def get_once(url: str) -> tuple[int, bytes, str]:
    # No retry wrapper: each allowed route has exactly one request opportunity.
    request = Request(url, method="GET", headers={"Accept": "*/*"})
    with urlopen(request, timeout=10) as response:
        return response.status, response.read(), response.headers.get_content_type()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--runtime-receipt", required=True, type=Path)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    receipt = json.loads(args.runtime_receipt.read_text(encoding="utf-8-sig"))
    require(receipt.get("url") == EXPECTED_ORIGIN, "Runtime receipt does not name the approved loopback origin.")
    require(receipt.get("version") == EXPECTED_VERSION, "Runtime receipt version differs from the scoped v18 preview.")
    source_commit = receipt.get("source_commit")
    require(isinstance(source_commit, str) and re.fullmatch(r"[0-9a-f]{40}", source_commit),
            "Runtime receipt must contain a full lowercase source_commit SHA.")
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    require(source_commit == head, "Runtime receipt source_commit differs from candidate HEAD.")

    endpoints = [
        ("root", EXPECTED_ORIGIN),
        ("app", EXPECTED_ORIGIN + "assets/app.js"),
        ("guide", EXPECTED_ORIGIN + "help/start.pdf"),
        ("runtime", EXPECTED_ORIGIN + "api/runtime/status/"),
    ]
    observed: dict[str, dict[str, object]] = {}
    for label, url in endpoints:
        status, body, content_type = get_once(url)
        require(status == 200, f"{label} GET did not return 200.")
        observed[label] = {"status": status, "content_type": content_type, "bytes": len(body), "sha256": sha256(body)}
        if label == "root":
            require(b'id="root"' in body, "Root response lacks the application root element.")
        elif label == "app":
            expected = (root / "assets" / "app.js").read_bytes()
            require(body == expected, "Served app.js differs from the candidate asset.")
        elif label == "guide":
            expected = (root / "docs" / "BoS_v18_Start_UA.pdf").read_bytes()
            require(body == expected, "Served guide differs from the candidate fixed PDF.")
        else:
            value = json.loads(body)
            require(value.get("version") == EXPECTED_VERSION, "Runtime status version is unexpected.")
            require(value.get("data_mode") == "demo", "Runtime status data_mode is not demo.")
            require(value.get("ai_configured") is False, "Runtime status ai_configured must be false.")
            observed[label]["fields"] = {
                "version": value["version"],
                "data_mode": value["data_mode"],
                "ai_configured": value["ai_configured"],
            }

    print(json.dumps({
        "schema": "bos.v18.local-availability-four-get.v1",
        "result": "PASS",
        "origin": EXPECTED_ORIGIN,
        "source_commit": source_commit,
        "observed": observed,
        "scope": "exactly four one-pass GET requests; no authentication, database, browser, external access, or product writes",
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
