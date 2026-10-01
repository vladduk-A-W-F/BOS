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

from bos_dev import atomic_json, read_json, state_lock

HOME_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "BOSDev"
TARGETS = {
    "main": "01a0be90-e790-7351-a8ac-059d523941c4",
    "integrator": "01a0dd56-ca2d-79c0-b159-bde80074a026",
    "writer": "01a0be9f-b413-7822-9f93-16ba69f4f00f",
    "observer": "01a0bf0f-a9e4-7631-87e1-bb1aed03f174",
    "design": "01a0bffa-3fc7-7bc2-9868-86164c6e0315",
    "quality": "01a0c05d-6eeb-79f1-a135-be66985b442f",
    "enablement": "01a0f2ce-270f-7ac3-bea0-1447f87aed61",
}
TOOLS = ("wait_threads", "read_thread", "send_message_to_thread")
MODELS = ("gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5")
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
    if old:
        if (old["target"] != target or old["sha256"] != digest
                or old.get("model") != model or old.get("thinking") != thinking):
            raise ChannelError("Message ID already belongs to different content, target, model or thinking.")
        if old["status"] == "ACKNOWLEDGED":
            return {"duplicate_suppressed": True, "delivery": old}
        raise ChannelError("Prior delivery is unresolved or failed; inspect the destination before any resend.")
    if any(v["target"] == target and v["sha256"] == digest for v in ledger["messages"].values()):
        raise ChannelError("Identical message already recorded; reuse its message ID to inspect delivery.")
    return None


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
    status_type = status.get("type") if isinstance(status, dict) else None
    completed_turn = (isinstance(turn, dict) and turn.get("status") == "completed"
                      and turn.get("error") is None)
    wake = result.get("wake")
    # A cold chat is eligible only for an explicit new assignment when the
    # fresh native response positively confirms this exact target is inactive.
    dormant_completed = (status_type == "notLoaded" and completed_turn
                         and isinstance(wake, dict) and wake.get("reason") == "inactiveStatus"
                         and wake.get("threadId") == target and wake.get("hostId") == "local")
    idle = status_type == "idle" and (turn is None or completed_turn)
    if (not isinstance(status, dict) or status.get("error") is not None
            or status.get("activeFlags", []) != [] or not (idle or dormant_completed)):
        raise ChannelError("Model override requires fresh idle or confirmed inactive unloaded target with a completed turn; no message sent.")
    return {"checked_at": now(), "thread_id": target, "status": status_type, "cursor": snapshot.get("cursor"),
            "eligibility": "dormant_completed" if dormant_completed else "idle",
            "latest_turn_id": turn.get("id") if turn else None,
            "latest_turn_status": turn.get("status") if turn else None}


def deliver(client, target, prompt, message_id, home=HOME_DIR, *, model=None, thinking=None):
    if target not in (TARGETS["main"], TARGETS["integrator"], TARGETS["writer"], TARGETS["observer"], TARGETS["design"], TARGETS["quality"], TARGETS["enablement"]):
        raise ChannelError("Sending is limited to the seven designated BOS tasks.")
    if target == os.environ.get("CODEX_THREAD_ID"):
        raise ChannelError("Do not send a wake-up message to the calling task itself.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", message_id):
        raise ChannelError("Invalid message ID.")
    if not prompt.strip() or len(prompt) > 20000:
        raise ChannelError("The message must contain 1..20000 characters.")
    options = model_options(model, thinking)
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    ledger_path = home / "codex-channel-delivery.json"
    preflight = None
    if options:
        # Suppress prior deliveries before polling. Never hold the shared state
        # lock across the MCP call; recheck the ledger when reserving the send.
        with state_lock(home):
            ledger = read_json(ledger_path) if ledger_path.exists() else {"schema": 1, "messages": {}}
            previous = prior_delivery(ledger, target, digest, message_id, model, thinking)
            if previous:
                return previous
        preflight = require_idle_model_target(client, target)
    with state_lock(home):
        ledger = read_json(ledger_path) if ledger_path.exists() else {"schema": 1, "messages": {}}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["mcp", "doctor", "status", "read", "send"])
    parser.add_argument("--target", choices=TARGETS, default="main")
    parser.add_argument("--targets", nargs="+", choices=TARGETS, default=["main", "writer", "design", "quality", "enablement"])
    parser.add_argument("--turn-limit", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--message-file", type=Path)
    parser.add_argument("--message-id")
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--thinking", choices=THINKING)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action != "send" and (args.model is not None or args.thinking is not None):
        parser.error("--model and --thinking are supported only by send.")
    model_options(args.model, args.thinking)
    if args.action == "mcp":
        return subprocess.call(
            list(installed_runtime()), stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    # PowerShell consumers and saved JSON use UTF-8 even on a Russian Windows locale.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    with AppTools() as client:
        if args.action == "doctor":
            result = {"checked_at": now(), "transport": "installed Codex App Tools MCP over stdio", "pipe_from_current_desktop_environment": True, "required_tools": {name: name in client.catalog for name in TOOLS}}
            if not all(result["required_tools"].values()):
                raise ChannelError("The desktop's fresh catalogue still lacks control tools.")
        elif args.action == "status":
            previous = read_json(HOME_DIR / "observer.json") if (HOME_DIR / "observer.json").exists() else {}
            cursor_keys = {"main": "main_cursor", "integrator": "integrator_cursor", "writer": "canonical_writer_cursor", "design": "design_cursor", "quality": "quality_cursor", "enablement": "enablement_cursor"}
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
            if not args.message_file or not args.message_id:
                raise ChannelError("send requires --message-file and --message-id.")
            result = deliver(client, TARGETS[args.target], args.message_file.read_text(encoding="utf-8-sig"), args.message_id,
                             model=args.model, thinking=args.thinking)
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ChannelError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
