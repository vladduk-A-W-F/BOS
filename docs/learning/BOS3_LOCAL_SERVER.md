# Local BoS 3.0 training instance

This launcher prepares one owner-managed synthetic BoS 3.0 instance at
`D:/3/BOSDev/local-bos3/owner`. It is loopback-only at
`http://127.0.0.1:8030/`; it is not a public link, HTTPS service, production
deployment, pilot approval or a replacement for the v18 review instance.

The source directory and instance root must be separate. Runtime state is stored
outside Git in `data`, `media`, `logs` and `state` below the instance root. The
launcher uses only the fixed path
`<root>/data/bos3-fasteners.sqlite3`; it does not derive a database path from
the source settings and it rejects roots or source paths marked `online-review`.
It also refuses a nonfresh root, an existing process receipt and a port already
bound on `127.0.0.1:8030`. It never removes an existing root, database, media
directory or process receipt.

The Django auth-session cookie has a stable, root-derived `bos3_session_...`
name, so a login or logout here cannot overwrite the old review session on the
same `127.0.0.1` host. The CSRF cookie deliberately remains the framework's
default `csrftoken`: the existing frontend reads that name. It is shared at the
host level, but it is not an authentication credential.

## Intended operator flow

After an independent review and explicit execution approval, run exactly once:

```powershell
scripts/bos3-local.ps1 init
```

The wrapper selects `D:/3/BOSDev/venv/Scripts/python.exe` only when that exact
file exists. Otherwise provide a concrete interpreter path, for example
`scripts/bos3-local.ps1 init -PythonPath D:/tools/bos3/python.exe`; it never
falls back to an arbitrary `PATH` Python.

The command creates a new SQLite database named `bos3-fasteners.sqlite3`, a
random personal CEO username/password, a random Django secret and the synthetic
fasteners fixture. The CEO is active but neither staff nor superuser; it receives
the existing document-view, download and workspace-export permissions. The owner
is bound by the fixture to the synthetic sales employee. The password and Django
secret are never printed or put in a Git file. The private user handoff file
`state/owner-access.json` contains only the local URL, username and password.
The Django secret is kept separately in `state/runtime-secrets.json` and is not
an owner-access artifact. Before any credential or log write, the launcher
creates and verifies protected Windows ACLs on the new instance root and its
`data`, `media`, `static`, `logs` and `state` directories. Those ACLs permit only
the current Windows user and `SYSTEM`; an ACL verification failure stops init.

Start, inspect and stop the owned local process with:

```powershell
scripts/bos3-local.ps1 start
scripts/bos3-local.ps1 status
scripts/bos3-local.ps1 stop
```

The PowerShell wrapper creates the child with `Start-Process -WindowStyle Hidden`.
The child receives a short-lived local launch nonce but does not start Django or
listen on the port until the parent has atomically recorded that nonce, the exact
PID, executable path, Windows creation time, source digest and command tokens in
the protected process receipt. If that receipt is never completed within 15
seconds, the child exits by itself before opening a listener. The nonce is only a
local correlation value, not a credential. Immediately after the gate and before
any Django import, the child recomputes the clean-source digest and rejects a
receipt or source tree that no longer matches.
Before status or stop, the controller verifies the receipt PID, executable path,
Windows creation time and source command arguments. A mismatch refuses to touch
the process. Stop retains the database, media, logs and credential file.

When `waitress` is already available in the selected Python environment, the
launcher uses it. It never installs a package. If it is unavailable, it records
and uses Django `runserver --noreload` as an explicitly local-review fallback;
that fallback is not a production server claim.

## Current integration boundary

`bos3_local_settings.py` supplies the separate data paths, loopback hosts,
empty AI key and `BOS3_TRAINING_ENABLED`. The BoS 3.0 authentication, CRM and
training behavior must be integrated by their owning cards before this launcher
is executed. In particular, an independent check must prove that passwordless
demo entry is disabled for this installation and that the training owner, observer
and CRM APIs have the intended access boundaries.
