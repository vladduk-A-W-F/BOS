# B30-D-CONTROL-HOME-FLOW-SOURCE: core dependency-binding review

**Reviewer:** `/root/bos3_candidate_review`  
**Mode:** focused static binding review. No code execution, test, import,
state read, transport, policy, cutover or runtime operation was performed.

## Verified delta

* `staged/bos_flow.py` is unchanged at SHA-256
  `f95394ea95132505cc792c87586397466c9c389c399295860f9452d684eee848`.
* `MANIFEST.json` SHA-256
  `02d2ec385e484ff3a1682529d03ba48db35aaea95581b85dc15b14fb79c9811f`
  and its report SHA-256
  `c15222d9739f17e78e9a4bdcdff9eac41e6ada7a8ddebd4b070abd42c5d697ab`
  bind the reviewed flow artifact to core interface
  `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497`,
  resolver provider `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`,
  and channel `3f1c4318a3693a47b088ca75742decbce84dda18942f97f039d424d392108a55`.
* The flow source contains no direct `channel.deliver` or
  `_deliver_resolved` reference. Its only channel invocation remains the
  subprocess CLI, receiving the already resolved explicit `--home` path.
  Therefore the repaired public delivery API does not introduce a direct
  signature dependency into this artifact.

## Verdict

**ACCEPT_SCOPED_STATIC_FLOW_CORE_BINDING**

The final dependency binding is coherent for this inactive source artifact.
This does not dynamically accept the channel CLI, establish a nonlegacy home,
authorize cutover, or advance runtime/readiness.
