# B30-11 local hosting static review

Date: 2026-09-27

Reviewed source (uncommitted isolated worker candidate):

```text
C:\Users\user\.codex\worktrees\bos3-fixture\repo\bos3_local_settings.py
C:\Users\user\.codex\worktrees\bos3-fixture\repo\scripts\bos3_local.py
C:\Users\user\.codex\worktrees\bos3-fixture\repo\scripts\bos3-local.ps1
C:\Users\user\.codex\worktrees\bos3-fixture\repo\docs\learning\BOS3_LOCAL_SERVER.md
```

## Verdict

`ACCEPT_SCOPED_STATIC` for the B30-11 local lifecycle design. No init, start,
stop, server, listener, network, browser, migration, seed, or test command was
executed in this review.

## Verified static boundaries

- The only runtime database path is `<root>/data/bos3-fasteners.sqlite3`; source
  and instance root must be separate, nonnested paths, `online-review` roots are
  rejected, and init requires an absent root.
- Windows ACLs are installed and checked before secret, owner-access, or log
  writes. ACL verification receives its path through the explicitly supplied
  `BOS3_ACL_VERIFY_PATH` environment variable rather than PowerShell positional
  `$args`.
- `owner-access.json` holds only URL, username and password; Django secret is
  kept only in `runtime-secrets.json`; both are inside protected state.
- Local authentication uses a stable root-derived `SESSION_COOKIE_NAME`, so it
  does not overwrite the existing review application's host-scoped session.
- The hidden child receives a fresh launch nonce and does not import Django or
  bind a listener until the parent atomically records exact PID, creation time,
  executable, source digest and command tokens. If the receipt remains absent
  or mismatched for 15 seconds, the child exits before listener startup.
- The child rechecks the clean source digest after the gate and before either
  waitress or runserver. Both runtime paths place the accepted source root on
  `sys.path` before application imports.
- Status/stop require PID, Windows creation time, executable and command-token
  verification; `TerminateProcess` is reachable only after that verification.

## Scope limits

This is static acceptance of a local loopback lifecycle implementation only.
It is not proof that the launcher starts on this host, that Windows ACL commands
behave as expected here, that the listener is reachable, or that application
authentication/CRM/training integration is complete. It does not raise
TECHNICAL_READY, PILOT_ALLOWED, MVP, production, external-hosting, invitation,
or release status.
