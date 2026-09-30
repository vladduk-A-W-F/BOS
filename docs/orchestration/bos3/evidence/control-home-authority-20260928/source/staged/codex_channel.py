"""BOS control channel through the installed, unmodified Codex App Tools MCP.

No app-server, browser helper, network listener, or second Codex executor is started.
The desktop supplies the current pipe through its process environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from bos_dev import CONTROL_HOME, ControlHomeError, CoordinationError, atomic_json, read_json, resolve_control_home, state_lock

HOME_DIR = CONTROL_HOME
TARGETS = {
    "main": "01a0be90-e790-7351-a8ac-059d523941c4",
    "integrator": "01a0dd56-ca2d-79c0-b159-bde80074a026",
    "writer": "01a0be9f-b413-7822-9f93-16ba69f4f00f",
    "observer": "01a0bf0f-a9e4-7631-87e1-bb1aed03f174",
    "design": "01a0bffa-3fc7-7bc2-9868-86164c6e0315",
    "quality": "01a0c05d-6eeb-79f1-a135-be66985b442f",
}
TOOLS = ("wait_threads", "read_thread", "send_message_to_thread")
MODELS = ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5")
THINKING = ("low", "medium", "high", "xhigh", "max", "ultra")


class ChannelError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def installed_runtime():
    if not os.environ.get("CODEX_APP_TOOLS_PIPE_PATH"):
        raise ChannelError("Run from a Codex desktop task: CODEX_APP_TOOLS_PIPE_PATH is absent. No server was started.")
    codex_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    plugin = codex_dir / "plugins/cache/openai-bundled/codex-app-tools"
    servers = [p for p in plugin.glob("*/server.mjs") if p.is_file()]
    if not servers:
        raise ChannelError("The installed codex-app-tools server.mjs was not found.")
    server = max(servers, key=lambda p: p.stat().st_mtime_ns).resolve()
    if not server.is_relative_to(plugin.resolve()):
        raise ChannelError("The bundled server path leaves its plugin directory.")
    candidates = [os.environ.get("CODEX_MCP_NODE_PATH"), os.environ.get("CODEX_BROWSER_USE_NODE_PATH")]
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "OpenAI/Codex/runtimes/cua_node"
    candidates += [str(p) for p in sorted(root.glob("*/bin/node.exe"), key=lambda p: p.stat().st_mtime_ns, reverse=True)]
    node = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if node is None:
        raise ChannelError("The installed Codex Node runtime was not found.")
    return str(node), str(server)


class AppTools:
    def __init__(self, command=None, timeout=25):
        self.timeout = timeout
        self.serial = 0
        self.messages = queue.Queue()
        self.proc = subprocess.Popen(
            list(command or installed_runtime()), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "bos-codex-control", "version": "1.0"},
            })
            self.write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            self.catalog = {t["name"]: t for t in self.rpc("tools/list", {}).get("tools", [])}
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put(ChannelError("Non-JSON response from bundled MCP server."))
                    return
        finally:
            self.messages.put(ChannelError("Bundled MCP server closed the connection."))

    def write(self, message):
        try:
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ChannelError("MCP connection closed while sending; outcome may be unknown.") from exc

    def rpc(self, method, params):
        self.serial += 1
        request_id = self.serial
        self.write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ChannelError(f"MCP timeout for {method}; do not automatically repeat a write.")
            try:
                response = self.messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise ChannelError(f"MCP timeout for {method}; do not automatically repeat a write.") from exc
            if isinstance(response, Exception):
                raise response
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise ChannelError(str(response["error"].get("message", "MCP request failed")))
            return response.get("result", {})

    def call(self, tool, arguments):
        if tool not in TOOLS or tool not in self.catalog:
            raise ChannelError(f"Required tool unavailable: {tool}")
        caller = os.environ.get("CODEX_THREAD_ID")
        if not caller:
            raise ChannelError("CODEX_THREAD_ID is absent; origin metadata must come from the calling task.")
        result = self.rpc("tools/call", {
            "name": tool, "arguments": arguments,
            "_meta": {"codexThreadId": caller},
        })
        if result.get("isError"):
            detail = " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
            raise ChannelError(detail or "App tool rejected the request.")
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        texts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except ValueError:
                pass
        return {"text": texts}

    def close(self):
        try:
            if not self.proc.stdin.closed:
                self.proc.stdin.close()
            if self.proc.poll() is None:
                self.proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            if self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=3)
        finally:
            self.reader.join(timeout=1)
            self.proc.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def model_options(model=None, thinking=None):
    if thinking is not None and model is None:
        raise ChannelError("--thinking requires an explicit --model to validate the combination.")
    if model is not None and model not in MODELS:
        raise ChannelError("Unsupported model override.")
    if thinking is not None and thinking not in THINKING:
        raise ChannelError("Unsupported thinking override.")
    if model == "gpt-5.5" and thinking in ("max", "ultra"):
        raise ChannelError("gpt-5.5 supports low, medium, high and xhigh thinking only.")
    return {key: value for key, value in (("model", model), ("thinking", thinking)) if value is not None}


def prior_delivery(ledger, target, digest, message_id, model, thinking):
    old = ledger["messages"].get(message_id)
    if message_id in ledger["messages"]:
        if (not isinstance(old, dict) or not isinstance(old.get("target"), str)
                or not isinstance(old.get("sha256"), str) or not isinstance(old.get("status"), str)):
            raise ChannelError("Message ID has an incomplete prior delivery record.")
        if (old["target"] != target or old["sha256"] != digest
                or old.get("model") != model or old.get("thinking") != thinking):
            raise ChannelError("Message ID already belongs to different content, target, model or thinking.")
        if old["status"] == "ACKNOWLEDGED":
            return {"duplicate_suppressed": True, "delivery": old}
        raise ChannelError("Prior delivery is unresolved or failed; inspect the destination before any resend.")
    for record in ledger["messages"].values():
        if not isinstance(record, dict):
            continue
        same_target = record.get("target") == target
        same_digest = record.get("sha256") == digest
        if (same_target and not isinstance(record.get("sha256"), str)) or (same_digest and not isinstance(record.get("target"), str)):
            raise ChannelError("Possible prior delivery is incomplete; inspect the ledger before sending.")
        if same_target and same_digest:
            raise ChannelError("Identical message already recorded; reuse its message ID to inspect delivery.")
    return None


def required_ledger(home):
    try:
        ledger = read_json(home / "codex-channel-delivery.json")
    except CoordinationError as exc:
        raise ControlHomeError("Control channel ledger is missing or invalid.") from exc
    if not isinstance(ledger, dict) or ledger.get("schema") != 1 or not isinstance(ledger.get("messages"), dict):
        raise ControlHomeError("Control channel ledger is missing or invalid.")
    return ledger


def validate_send(target, prompt, message_id, model=None, thinking=None):
    require_delivery_target(target)
    if not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", message_id):
        raise ChannelError("Invalid message ID.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise ChannelError("The message must contain 1..20000 characters.")
    return model_options(model, thinking)


def require_idle_model_target(client, target):
    result = client.call("wait_threads", {"targets": [{"threadId": target, "hostId": "local"}], "timeoutMs": 0})
    polls = result.get("polls") if isinstance(result, dict) else None
    if (not isinstance(polls, list) or len(polls) != 1 or result.get("error") is not None or result.get("errors")
            or not isinstance(polls[0], dict)):
        raise ChannelError("Model override requires one fresh confirmed idle target; status is unknown.")
    snapshot = polls[0]
    thread = snapshot.get("thread")
    if (not isinstance(thread, dict) or thread.get("id") != target or thread.get("hostId") != "local"
            or snapshot.get("error") is not None or thread.get("error") is not None):
        raise ChannelError("Model override target identity or error state is unknown; no message sent.")
    status = thread.get("status")
    turn = snapshot.get("latestTurn")
    if (not isinstance(status, dict) or status.get("type") != "idle" or status.get("error") is not None
            or (turn is not None and (not isinstance(turn, dict) or turn.get("status") != "completed"
                                     or turn.get("error") is not None))):
        raise ChannelError("Model override requires idle with a completed or absent last turn and no error; no message sent.")
    return {"checked_at": now(), "thread_id": target, "status": "idle", "cursor": snapshot.get("cursor"),
            "latest_turn_id": turn.get("id") if turn else None,
            "latest_turn_status": turn.get("status") if turn else None}


def require_delivery_target(target):
    if target not in (TARGETS["main"], TARGETS["integrator"], TARGETS["writer"], TARGETS["observer"], TARGETS["design"], TARGETS["quality"]):
        raise ChannelError("Sending is limited to the six designated BOS tasks.")
    if target == os.environ.get("CODEX_THREAD_ID"):
        raise ChannelError("Do not send a wake-up message to the calling task itself.")


def _deliver_resolved(client, target, prompt, message_id, home, *, model=None, thinking=None):
    """Internal path: caller already resolved home before AppTools startup."""
    options = validate_send(target, prompt, message_id, model, thinking)
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    ledger_path = home / "codex-channel-delivery.json"
    preflight = None
    if options:
        # Suppress prior deliveries before polling. Never hold the shared state
        # lock across the MCP call; recheck the ledger when reserving the send.
        with state_lock(home):
            ledger = required_ledger(home)
            previous = prior_delivery(ledger, target, digest, message_id, model, thinking)
            if previous:
                return previous
        preflight = require_idle_model_target(client, target)
    with state_lock(home):
        ledger = required_ledger(home)
        previous = prior_delivery(ledger, target, digest, message_id, model, thinking)
        if previous:
            return previous
        ledger["messages"][message_id] = {
            "target": target, "sha256": digest, "status": "SENDING",
            "created_at": now(), "message_id": message_id,
            "model": model, "thinking": thinking,
        }
        if preflight is not None:
            ledger["messages"][message_id]["model_preflight"] = preflight
        atomic_json(ledger_path, ledger)
    try:
        receipt = client.call("send_message_to_thread", {"threadId": target, "hostId": "local", "prompt": prompt, **options})
    except BaseException:
        with state_lock(home):
            ledger = read_json(ledger_path)
            ledger["messages"][message_id].update(status="UNCONFIRMED", updated_at=now())
            atomic_json(ledger_path, ledger)
        raise
    with state_lock(home):
        ledger = read_json(ledger_path)
        ledger["messages"][message_id].update(status="ACKNOWLEDGED", updated_at=now(), receipt=receipt)
        atomic_json(ledger_path, ledger)
    return {"duplicate_suppressed": False, "delivery": ledger["messages"][message_id]}


def deliver(target, prompt, message_id, home=HOME_DIR, *, model=None, thinking=None):
    """Public send API: refuse home and target before opening AppTools."""
    home = resolve_control_home(home)
    validate_send(target, prompt, message_id, model, thinking)
    required_ledger(home)
    with AppTools() as client:
        return _deliver_resolved(client, target, prompt, message_id, home, model=model, thinking=thinking)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["mcp", "doctor", "status", "read", "send"])
    parser.add_argument("--target", choices=TARGETS, default="main")
    parser.add_argument("--targets", nargs="+", choices=TARGETS, default=["main", "writer", "design", "quality"])
    parser.add_argument("--turn-limit", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--message-file", type=Path)
    parser.add_argument("--message-id")
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--thinking", choices=THINKING)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--home", type=Path)
    args = parser.parse_args()
    if args.action != "send" and (args.model is not None or args.thinking is not None):
        parser.error("--model and --thinking are supported only by send.")
    home = None
    if args.home is not None or args.action in {"status", "send"}:
        home = resolve_control_home(args.home)
    model_options(args.model, args.thinking)
    if args.action == "mcp":
        return subprocess.call(
            list(installed_runtime()), stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    # PowerShell consumers and saved JSON use UTF-8 even on a Russian Windows locale.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    send_prompt = None
    if args.action == "send":
        if not args.message_file or not args.message_id:
            raise ChannelError("send requires --message-file and --message-id.")
        send_prompt = args.message_file.read_text(encoding="utf-8-sig")
        validate_send(TARGETS[args.target], send_prompt, args.message_id, args.model, args.thinking)
        required_ledger(home)
    with AppTools() as client:
        if args.action == "doctor":
            result = {"checked_at": now(), "transport": "installed Codex App Tools MCP over stdio", "pipe_from_current_desktop_environment": True, "required_tools": {name: name in client.catalog for name in TOOLS}}
            if not all(result["required_tools"].values()):
                raise ChannelError("The desktop's fresh catalogue still lacks control tools.")
        elif args.action == "status":
            with state_lock(home):
                previous = read_json(home / "observer.json")
            cursor_keys = {"main": "main_cursor", "integrator": "integrator_cursor", "writer": "canonical_writer_cursor", "design": "design_cursor", "quality": "quality_cursor"}
            targets = []
            for alias in dict.fromkeys(args.targets):
                target = {"threadId": TARGETS[alias], "hostId": "local"}
                cursor = previous.get(cursor_keys.get(alias, ""))
                if cursor:
                    target["afterCursor"] = cursor
                targets.append(target)
            result = client.call("wait_threads", {"targets": targets, "timeoutMs": 0})
        elif args.action == "read":
            result = client.call("read_thread", {"threadId": TARGETS[args.target], "hostId": "local", "turnLimit": args.turn_limit, "includeOutputs": False, "maxOutputCharsPerItem": 1500})
        else:
            result = _deliver_resolved(client, TARGETS[args.target], send_prompt, args.message_id,
                                       home, model=args.model, thinking=args.thinking)
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ChannelError, ControlHomeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
