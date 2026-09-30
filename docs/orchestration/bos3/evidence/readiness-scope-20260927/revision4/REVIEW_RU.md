# B30-12 learning oracle revision 4

2026-09-27. Independent reviewer start_overview_review. Source f55a15de4006d10c0d7c65f8a2ca8499fbb99819. Oracle SHA256 32b8ecd2c6a0d1a5fb25eed59d3774acd25350874e704c795cd869f170f9d722; author report fa83ce4926277c4855a17720395ba5794e0caed5295d89843931fda1388f8594.

Verdict REVISE_BEFORE_OWNER_EXCEPTION. No execution. P1: common mutation routing incorrectly uses /api/erp/preview/ for all commands; ERP alone uses it, create_task/crm_handoff use /api/operations/preview/, then common confirm. P1: empty isolated DB plus pre-existing active owner is not an executable bootstrap. Need exact reviewed one-run harness/command, explicit schema/user/ceo setup scope, protected normal auth/relogin, marker-derived payloads, requests/proposals/receipts and hashes, stop-on-first mismatch; no credentials in evidence. P2: C1 must assert full completed status and all four steps, with reload/relogin receipt.

Existing author received these findings for static correction and harness preparation in the same scratch. No new exception or execution is granted. Any final dev4 candidate needs a separate static source-blob applicability review before this f55-derived oracle can be proposed. Historical caps and false readiness remain.
