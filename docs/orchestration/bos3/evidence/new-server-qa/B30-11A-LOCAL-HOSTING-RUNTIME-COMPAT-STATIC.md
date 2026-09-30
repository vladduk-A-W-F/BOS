# B30-11A local hosting runtime compatibility static review

Date: 2026-09-27

## Verdict

`ACCEPT_SCOPED_STATIC` for the venv redirector / actual Python process identity
correction in the B30-11 local lifecycle candidate.

No init, start, stop, listener, network, database, seed, migration, test or
browser command was executed by this reviewer.

## Reviewed guarantees

- `sys.executable` remains the venv launcher, while the controller first proves
  its actual Windows process image equals the normalized
  `sys._base_executable` image. Parent, child gate and status/stop all require
  that same expected actual image.
- The `Start-Process` PID is deliberately non-authoritative. The real
  `internal-serve` child writes a protected, atomic nonce-bound announcement
  containing its own PID, creation time, image, source/digest, runtime and
  exact tokens before it can import Django or bind a listener.
- Parent independently verifies the announced live process with PID, creation
  time, expected image and command-token checks, then writes the canonical
  process receipt. Only a receipt exactly matching the child self-record opens
  the gate.
- A parent failure before canonical identity receipt leaves the child blocked;
  it times out within 15 seconds and self-removes its announcement before any
  listener. A `start_failed` receipt likewise never opens the gate.
- Source is cleanly digested before start and again by the child after the gate,
  before Django application import. `sys.path` includes the accepted source for
  both waitress and runserver paths.
- ACL code now treats `icacls` output as raw bytes and checks its return code,
  avoiding localized output decoding as a lifecycle dependency.

## Limits

This is a design/code review, not runtime evidence. The separate B30-QH01
fixture test guard failure remains an open evidence gate; this review does not
convert it into a seed or initialization PASS. No technical, pilot, production,
external-hosting, invitation or release readiness is raised.
