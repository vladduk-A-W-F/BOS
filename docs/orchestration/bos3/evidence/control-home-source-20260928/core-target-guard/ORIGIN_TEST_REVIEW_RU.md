# B30-D-CONTROL-HOME-CHANNEL-TEST-SOURCE: independent static review

**Reviewer:** `/root/bos3_candidate_review`  
**Mode:** static source review only. No import, parser, compile, test,
transport, state/ledger/home, policy, process, network or runtime action ran.

## Verified scope

* The staged test SHA-256 is
  `c1b6f8ddc695dad2b56f27ad1540e89791793f8b95e97d546f83558a2f91809c`;
  manifest SHA-256 is
  `6ec7ab4377e006d4b286d32309bd21623c8bee02a0995ce662f174fc96cf9335`;
  report SHA-256 is
  `090ae5a7c9fdac7014b616b4c39f1c1185a523f0ef3a59306542051956fe8224`.
* The test imports sibling `core/staged`, not the live legacy tools path. Its
  synthetic helper patches only resolver, lock and `AppTools`, supplies a
  context-manager-capable `FakeClient`, and retains the temporary test ledger.
  The existing duplicate, changed/new ID, exact target/prompt, UNCONFIRMED
  no-resend, designated routing and protocol-EOF assertions remain present.
* The distinct nonlegacy-home case does not patch the resolver and asserts
  `AppTools` constructor is not called. That correctly covers refusal of a
  nonlegacy unestablished home before public transport construction.

## Finding

### P1: outside/self test does not preserve refusal before transport construction

The public provider entry `deliver()` resolves home, then enters
`with AppTools()` before calling `_deliver_resolved()`, where outside/self
target checks occur. The adapted `test_outside_target_and_self_are_rejected`
only asserts `FakeClient.calls == []`; its patched `AppTools` factory returns
the fake directly and does not record whether construction occurred. Thus it
proves no synthetic `client.call`, but not the card's stated outside/self
refusal-before-transport property.

This review does not infer that the constructor performs a live send. The
problem is the unproven and currently false-as-ordered stronger assertion,
not a dynamic claim.

**Required repair boundary:** first make a separately reviewed core public
API change that validates designated target and self before `AppTools()` is
constructed, or explicitly narrow the accepted contract so the preserved
assertion means only no `client.call`. Under the current card contract, the
test must then use a constructor mock and assert it was not called for
outside/self cases, and be rebound to the repaired core pin. Do not weaken
duplicate, uncertainty or target assertions; do not run the test merely to
decide this static ordering defect.

## Verdict

**REVISE_BEFORE_SCOPED_TEST_SOURCE_ACCEPTANCE**

Synthetic isolation and the nonlegacy refusal seam are otherwise appropriate,
but the target/self transport-order preservation is not demonstrated against
the actual public provider order. This verdict is not a dynamic test result,
cutover, runtime or readiness claim.
