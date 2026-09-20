# BOOTSTRAP-OWNER

Problem: a migrated empty isolated BoS installation has no business owner onboarding command. A Django superuser without exactly one BoS role cannot use the normal business login; gate 8 only constructs fixture identities internally.

Scope: add `operations/management/commands/bootstrap_bos_owner.py`, `operations/test_bootstrap_owner.py`, and `docs/FIRST_OWNER_UA.md` in the assigned `owner-copy` worktree. No schema, launcher, API, UI, STATE/QUEUE, source DB, runtime configuration, or privileged deployment changes. No commit or push by the author.

Contract:

- Explicit working mode and a migrated empty database; only Django Permission/ContentType bootstrap rows allowed.
- Nonempty managed tables, users, groups, configuration, sessions, archived data or a previous marker cause refusal without cleanup/elevation.
- Password is taken via hidden interactive confirmation or one stdin line, never an argv option. Minimum 12 and maximum 512 characters; common/numeric/similarity checks plus explicitly configured validators.
- Exactly one active CEO role, no employee auto-creation, no implicit staff/superuser.
- Document download and workspace export permissions are explicit flags, with exact content type matching. Existing CEO read policy remains unchanged.
- Unique Configuration marker inserted before reads inside transaction; user, fresh group, explicit permissions, marker contents and nonsecret audit are atomic. Unique-key/database writer lock excludes a second successful concurrent bootstrap.
- Fail closed on database conflict, preserving existing data and not leaking SQL/credentials.
- Intended before any application writers start; serializes bootstrap commands, not arbitrary external writers.

Evidence: `sqlite-attempt-1/raw.log` and receipt: 16 new-card tests PASS, 5.998 seconds test-body time, real Django PBKDF2/login/CSRF/identity/Policy, opt-in permission boundaries, bad input/refusal/no-overwrite, missing requested permission rollback, two real database connections create exactly one owner. This is not a full acceptance gate or PostgreSQL claim. `manifest.json` fixes the reviewed three file bytes; `BOOTSTRAP-OWNER.patch` creates exactly those files. Python 3.12.14 / Django 6.0.5 / DRF 3.17.1.

Independent reviewer should inspect the atomic empty check, role/permission escalation boundary, concurrency result, password handling including non-TTY behavior, and exact patch/manifest/raw output. Author did not accept their own change.

Review correction: root's independent reviewer reported getpass warning fallback could echo input even when stdin is a TTY. Both prompts now promote GetPassWarning to a caught error before any fallback input. The new test calls real fallback_getpass on prompt 1 and prompt 2, verifies no _raw_input call and no records. `sqlite-warning/raw.log` verifies this one new regression only (PASS, 0.197 s); the earlier 16 were not needlessly rerun on SQLite. Its receipt pins the corrected command and updated test source.

PostgreSQL 16.15 was explicitly authorized locally by root after recorded binary provenance. A new isolated cluster listens only on 127.0.0.1:55439. The non-superuser verification role has CREATEDB only. Each test run gets its own bos_verify_<16hex> database; the owner runner proves empty source before/after and drops only its allocated source/test database names. `pg-cluster-proof.json` contains actual nonsecret version/host/role facts; credentials are outside Git in the private pg-secrets directory. No installer, Windows service, production activation or full suite was run.

Final PostgreSQL run: `pg17/raw.log`, `pg17/receipt.json`, 17/17 PASS in 25.951 s test-body time (52.578 s wrapper interval). Actual worker connections reported PostgreSQL 160015 and `test_bos_verify_a9251794c89e4e4b`; distinct connections 2, exactly one created and one refused. Source `bos_verify_a9251794c89e4e4b` had 0 public tables before and after. Source/test allocated databases were removed and absence verified (`cleanup=true`). Source file SHA unchanged. Raw SHA256: `65d8ab9c550cef9ebfe6044464758eb4f65b42be62febd37c19477fc363dccd6`. Cluster remains available to root and sibling agents for independent allocated databases; only root should stop it after coordinated use.
