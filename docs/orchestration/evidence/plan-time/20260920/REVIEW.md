# Independent PLAN-TIME review

Reviewer: time_probe_final_review. Result: **ACCEPT_SCOPED_PLAN_TIME_EVIDENCE — F04 and F05**.

## Prepared experiment

The reviewer read the actual recovered files, checked PostgreSQL identity and disposal guards, independent child timeout, companion-database ownership, unchanged business assertions, report contracts, and limited workflow scope. The final change to the recovered supervisor was only SOURCE_BASE; the card's timeout wording and publication base were corrected.

Accepted SHA256:

- plan_time_probe.py: c495cd26b85e31861e635f13790be267fae25c2cd21b7a761db1dcc467dd8a00
- plan_time_django.py: 08b9af4ea85ebafe6dfc1cb9aad6cbaffcb5878222dc117c200b2c491268b01a
- plan_time_replay.py: ef2de845d1719765bed6787d5784051f9032cc32be04896d758e9da93dffe862
- bos-plan-time-targeted.yml: cf47993e39c9dcdf83c353796028f5c7b9c10ef0323eb1d0097736206cb444ec
- original prepared card: f7fc99ab137dcdca5cebe740f038348e7d1e570626305ce24de59d159338fb84

Five preserved local stdlib controls passed before publication, including a real child kill at 1.031 seconds despite a 2-second observer. The reviewer inspected control definitions and retained log hashes. That historical local control report does not itself bind a final harness SHA and is not described as a new CI test run.

## Evidence-only reader

Result: **ACCEPT_SCOPED_EVIDENCE_READER**. Independently read blob 3e7fe29903b11c3c1adfce8496046e3e84681d4d: 7163 bytes, SHA256 4acf814b76353daca0bdc8600198830250ef05f1a7d1147e499adc35eaca98f1.

Fixed run/artifact identity, size, ZIP digest, allowed members, type/size checks, index checks, numbered chunks and terminal manifest were reviewed. The reader has no checkout, application/DB execution or archive-code execution; storage requests do not carry the GitHub Authorization header.

Diagnostic run 35513613026, attempt 1, commit 1876ad00412b558fcfe0f23ab5291c90caeba63a: success.
Reader run 35514074336, commit 56a718116577799cca5c098b427b88322b60cd82: success.
A separate live API read confirmed diagnostic targeted job 106086955521 on reader commit: SKIPPED.

## Independent artifact and result checks

Reviewer fetched job 106086930483 logs independently and accepted only timestamped transport markers: BEGIN 1, MEMBER 12, PART 40, END 1. Chunk order, lengths, final manifest and provenance matched.

Reviewer reconstructed the original ZIP in memory using .NET: 22338 bytes, SHA256 1fd89539b1fd46fbd27a6b8a79549aad00288519a6ead3b78032749fbb0d53fb, 11 archive members, all 10 SHA-index entries verified. Coordinator separately checked the same original bytes with offline Python stdlib.

F04: Found 1 / Ran 1 / OK, three currency subtests, three A06_PAIR and three A06_PASS, six overlapping worker HTTP 200 responses. Actual PostgreSQL 16.15 source/test identities, one effect, unchanged replay, source canary, database cleanup and runtime SHA verified. Sample 6.801 seconds; worker 6.431; test body 1.589567; DB setup 2.533410. Two real PBKDF2 encodes use 1200000 iterations each. 2740 SQL execute calls across seven thread records, zero SQL errors. SQL-time summed across threads is not elapsed time.

F05: one sequence, four replays, six HTTP 200 responses. Actual issued PostgreSQL 16.15 database had zero user tables before migration. All 55 managed-model table counts, including M2M tables, matched after rollback. Eight global fingerprints each execute 24 SQL queries (192 total, 0.134974337 seconds of function wall time); four full snapshots execute 148 SQL queries (0.099370786 seconds). Cached replay phases call no fingerprint/snapshot, while the following oracle does; mutex remains. The retained redundant oracle has a 24-query fingerprint of 0.015666313 seconds plus Event.count. No SQL errors were reported.

The replay phase clock starts before print/self.save. Therefore unused_original_oracle phase 0.192883621 seconds includes instrumentation and cannot be attributed entirely to the fingerprint/product. The approximately 21–22 ms cached replay phases are instrumented phase times, not clean HTTP benchmarks. Five-second wait polling cannot rule out brief lock waits between samples.

## Scope

Acceptance covers two completed current diagnostic samples. It does not establish the cause or resolution of either historical 600-second timeout. No runtime fix or full rerun follows from these results.

P06 BLOCKED; root_cause_proven=false; technical_ready=false; pilot_allowed=false; historical P05 remains 3/3.
