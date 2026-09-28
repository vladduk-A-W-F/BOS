# B30-D-CONTROL-HOME-FLOW-SOURCE: independent static review

**Reviewer:** `/root/bos3_candidate_review`  
**Mode:** static source reading only. No import, parser, compile, test, CLI,
state/config/ledger/queue/lock read, network, policy or runtime action ran.

## Exact subject

* Reviewed source: `D:/3/BOSDev/setup/bos_flow.py`, SHA-256
  `8399627333ef9624d8161503224b32ecc8e537a6fe9bf08852c24267b5c9fb24`.
* Reviewed staged result: `staged/bos_flow.py`, SHA-256
  `f95394ea95132505cc792c87586397466c9c389c399295860f9452d684eee848`.
* The stated core interface/provider/channel pins are treated as dependency
  inputs, not dynamically accepted behavior in this review.

## Findings

No P0-P2 static regression found within the assigned flow allowlist.

1. Legacy `HOME_DIR/tools` import precedence is removed. The flow imports
   `resolve_control_home` and `ControlHomeError` from `ROOT/setup` before any
   flow entry resolves selected home, eliminating the prior selected-home vs
   import-source mismatch.
2. `refresh()` resolves home before `state_lock`, observer/config access and
   `local_flow.collect`; `handoff()` resolves home before reading the packet or
   preparing messages. Every in-file `prepare_handoff` call receives that
   resolved Path, leaving no default legacy-home direct path.
3. CLI `--home` is validated for `models`, `status` and `next`, so a selected
   nonlegacy unestablished home fails through the resolver rather than being
   silently ignored by read-only index actions. `ControlHomeError` is caught
   in the existing command error boundary.
4. The resolved Path is passed unchanged to state locks and to channel as
   explicit `--home`. Actor list, policy checks, reference checks, handoff
   admission conditions, transport executable, root report locations and
   `local_flow` module calls otherwise remain unchanged in the diff.

## Limits

This is inactive partial source preparation. Resolver behavior, channel CLI
compatibility, nonlegacy authority establishment, external wrappers, actual
state paths, locks, transport and any cutover remain unexecuted and outside
this verdict.

## Verdict

**ACCEPT_SCOPED_STATIC_FLOW_SOURCE_PREPARATION**

The patch may proceed only as a dependency-bound source artifact for later
separate integration/review. It does not establish a control home, authorize
a switch or runtime action, or prove compatibility dynamically.
