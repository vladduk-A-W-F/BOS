# B30-D-CONTROL-HOME-CORE-SOURCE: archival/control integration review

**Reviewer:** `/root/bos3_candidate_review`  
**Mode:** read-only static archive and control-record review. No helper import,
test, compile, state/home/ledger/policy/process/network or runtime action ran.

## Verified archival fidelity

The canonical archive `evidence/control-home-source-20260928/core/` contains
the exact core card plus the seven manifest/review/source artifacts. The card
matches `CORE_CARD.json` byte-for-byte:
`4e68f8ffdb4e1ffee20194501e708f250837dbeeefdbd6747769a78b13aacb37`.

All seven copied core artifacts match their frozen source bytes and hashes:

* `staged/bos_dev.py` — `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`;
* `staged/codex_channel.py` — `3f1c4318a3693a47b088ca75742decbce84dda18942f97f039d424d392108a55`;
* `INTERFACE.json` — `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497`;
* `REPORT_RU.md` — `5a5319a7452c8045d2a6ae49e466f90917704be25bb2f81a1b3f325806009cc4`;
* `MANIFEST.json` — `7952f641f0e7ca7a52ba93a93b4cc601c78b6a3df660299b44c66c563dd5aefa`;
* initial review — `13f9595d9d480076c4f3f9ac7e20e492f5b99ae666e54d767261a2ca0a891172`;
* accepted repair review — `b7186966fd0ec1a443ae2a1120ea4736ae602c8c143a4040a9436a2cbd54bc3c`.

The initial P1 and its focused accepted closure are retained separately rather
than rewritten. The archive README correctly describes artifacts as inactive,
not installed helpers or a runtime release.

## Control consistency

`CONTROL_STATE.json` accurately records core and flow as static accepted,
with wrappers as the only active source-only line. It preserves no live install,
home switch, state/ledger copy, execution, runtime or readiness claim. Flow is
accepted but not yet archived; its sequential archival remains distinct from
the core copy. The blocked runtime-diagnostic owner decision and existing caps
are not broadened by this integration.

Current C65 map status is explicitly
`STATIC_MAP_ACCEPTED_SCOPED_WRAPPER_SOURCE_ASSIGNED`. Its only next owner is
`bos3_channel_diagnosis`; the assigned `WRAPPERS_CARD.json` binds the final
flow source and review `9beb9790de869bed59f665845b3480770d58d39dd384c60bbc6f8409e8ed117b`,
plus the accepted core/interface pins. It retains the no-live-edit, no startup,
no registration, no state-copy and no-cutover boundary. The older P1 review is
still preserved under the explicit `supersedes_initial_review_transition`
record rather than treated as a current failure.

## Verdict

**ACCEPT_SCOPED_INACTIVE_CORE_ARCHIVE_AND_CONTROL_INTEGRATION**

The exact core archive and its current control record are suitable for a
documentation-only canonical integration. This does not authorize core/flow
installation, wrapper execution, authority establishment, cutover, runtime
activation or readiness promotion.
