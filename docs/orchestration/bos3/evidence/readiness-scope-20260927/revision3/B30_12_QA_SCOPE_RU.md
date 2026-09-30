# B30-12 · подготовка scope для current-candidate QA

## Статус и граница

Это read-only подготовка для кандидата `f55a15de4006d10c0d7c65f8a2ca8499fbb99819`.
Она не является dynamic QA, полным verdict готовности, разрешением на setup,
seed, миграции, browser, HTTP, CLI validator, build или запись в canonical
репозиторий. Единственный интегратор — root. До исполнения нужен независимый
reviewer `start_overview_review` и отдельный точный owner exception.

Входы: `FULL_READINESS_MATRIX.json` SHA-256
`61c9cb6ec47398a4d5cc61d8cb70b1c2f430a7c314c07064efa10b8dea1146e7`
и `FULL_READINESS_RU.md` SHA-256
`2a22338052950005b10b78415da0e95861961353a12a7051c38af5e981402332`.
Дополнительный exact-source input для S2: `S2_SOURCE_TRACE_F55.json` SHA-256
`95b24362827af83877a4939d23f100e18cfab03d310890465be7d8087e4f1f14`
и `S2_SOURCE_TRACE_F55_RU.md` SHA-256
`93fc91f2f5adbd86230d0e24219e7a00ae09b22b54e03924adb1b997c6655eb9`.

## Требования, existing evidence и gap

| Scope | Existing code/evidence | Current gap | Future oracle/reviewer |
|---|---|---|---|
| S1 order → reserve/shipment → invoice/payment | B30 supply/quality/payment preview, historical scoped server evidence | current exact candidate lacks an end-to-end trace and receipt reconciliation | candidate-bound trace oracle; `start_overview_review` |
| S2 document → draft → reconcile → confirm | exact-f55 source trace: CEO document-match read, operation preview/confirm and supplier-invoice registration path | code path is mapped statically; final current-candidate dynamic proof remains absent | separate S2-only authorisation decision and `start_overview_review` |
| S3 shortage → procurement/move → receipt/quality → stock | preview presentation and historical server QA | no current candidate full chain, receipt or stock reconciliation | candidate-bound stock/receipt oracle; `start_overview_review` |
| UXD-01…08 | implementation/history exists, including static/build/entry evidence | none is traced to final current-candidate acceptance | eight-row trace matrix before any UI run |
| Gates 1–11 | historical evidence preserved | gates 1–4, 6–7 and 11 are not proven; 5 is exhausted; 8 is outside owner-local scope; 9 remains A10; 10 is entry-only partial | separate gated plan, never inferred from B30 delivery |

No row above assigns implementation rewrites. An untraced requirement is not a
claim that the implementation is absent.

## Three-case future contract

Each future case must identify the authenticated role, allowed command/service
steps, expected receipt ID and immutable input/output hashes, UAH amount and
currency, state transitions, and reload/relogin/resume assertion for a
completed step.

1. **S1**: order → reserve/shipment → invoice → payment; require UAH totals
   before/after and a receipt that excludes duplicate payment creation.
2. **S2**: source document → extracted draft → reconciliation → explicit
   confirmation; require source identity, proposal/receipt identity and a
   separately feasible reload/relogin preservation assertion. The supplied
   source trace does not itself prove a live session or reload/relogin result.
3. **S3**: shortage → procurement or movement → receipt → quality → stock;
   require shortage/receipt/quality/stock transition evidence and UAH or unit
   conservation as applicable.

Any case that cannot express these facts is not runnable under B30-12.

## Synthetic-environment design — not created

A future isolated synthetic environment must use a newly named directory,
database and media root outside owner-local runtime. It must seed only
synthetic identities and record a manifest before write operations. Expected
writes, if separately authorized, are:

- ERP: order, reserve/shipment, invoice, payment and inventory receipt/move.
- S2: only the mapped supplier-invoice registration records named below; it
  does not authorize a CRM write.

Owner data, media, credentials, local runtime database, secrets and canonical
working tree are preservation targets and may not be read for values, reset,
seeded, migrated, or written. Teardown is not implicit; retention/deletion is
a later owner decision.

## Revision 3 · candidate-bound mapping and non-executable rows

The following table corrects the first preparation. B30 preview content is
educational presentation; it is not an authorization or proof for broader
operational S1/S2/S3. No row below is executable without a later exact
owner exception.

| ID | Exact candidate code / evidence | Role and route boundary | Proposed receipt/state fact | Status and future oracle | Stop condition |
|---|---|---|---|---|---|
| B30 supply presentation | `frontend/bos3_content.json`, `BOS3-CASE-01`, `frontend/boss_app_source.html` `Bos3EntryCase` / `Bos3TrainingHub` | unauthenticated preview then authenticated training; no ERP writer route | chart facts only: 140 + 360 = 500 комплектів; deficit 120 шайб; no operational receipt | NEW static traceability row; presentation oracle only | any request to reserve, purchase, receive or write ERP stops scope |
| B30 quality presentation | `frontend/bos3_content.json`, `BOS3-CASE-02`; same UI symbols | preview then authenticated training; no quality writer route | 250 + 20 = 270 units represented; 20 blocked; no quality receipt | NEW static traceability row; presentation oracle only | any request to change lot/quality state stops scope |
| B30 payment presentation | `frontend/bos3_content.json`, `BOS3-CASE-03`; same UI symbols | preview then authenticated training; no finance writer route | 10,000 + 6,400 = 16,400 UAH represented; no payment receipt | NEW static traceability row; presentation oracle only | any request to post/confirm payment stops scope |
| S1 operational chain | `frontend/boss_app_source.html` `erpFetch`, `ERP_ACTIONS`; historical B30 source is insufficient | authenticated ERP role and exact UI/API route are **unmapped** | order/reserve/shipment/invoice/payment receipt IDs, UAH before/after, reload/relogin completed state | BLOCKED; a candidate-bound source mapping must precede any oracle | unknown role/route, receipt schema or payment/network cap intersection |
| S2 document chain | exact-f55 blobs pinned by `S2_SOURCE_TRACE_F55.json`: `erp/urls.py`, `erp/views.py`, `operations/urls.py`, `operations/service.py`, `operations/document_matching/{commands.py,server_adapter.py,registration.py}`, `boss_project/policy.py` | **CEO only**: `GET /api/erp/purchases/<pk>/document-match/`, then `/api/operations/preview/` and `/api/operations/confirm/`; command `register_supplier_invoice`, policy `erp_register_supplier_invoice` | verified source/document identity → draft/reconciliation → one `SupplierInvoiceRegistration`, one `Event`, receipt `supplier_invoice_registration_id` + `invoice_matching_status=matched`; replay/conflict guards are source-mapped | `MAPPED_STATIC_FINAL_DYNAMIC_EVIDENCE_UNCONFIRMED`; separate S2-only decision, excluded from three-case combined exception | any role/route/blob/payload mismatch; any write beyond mapped allowlist; claimed session persistence without a separately reviewed assertion |
| S3 operational chain | `frontend/boss_app_source.html` `ERP_ACTIONS` includes `transfer_dispatch` / `transfer_receive`; current B30 content is presentation only | authenticated ERP role and exact API/service symbols are **unmapped** | shortage → procurement/move → receipt → quality → stock receipt IDs and units | BLOCKED; separate source mapping required | unknown writer/service, unit conservation or receipt schema |

UXD-01…08 are also separate trace rows, each requiring: exact source path and
symbol; role/route; source/period/branch/freshness or list/record/history fact
as relevant; evidence file; applicable candidate commit; an oracle assertion;
and one stop condition. UXD-08 must additionally capture currency/role/preview
and confirm identity. No UXD row grants a writer action.

### S2 exact-source boundary

The source trace covers 13 f55-pinned blobs, including three unexecuted test
files: `erp/test_document_match_route.py`,
`operations/test_document_matching_server.py`, and
`operations/test_supplier_invoice_registration.py`. The mapped read schema is
`bos.document-match-read.v1`; the operation payload is `document_id`,
`purchase_id`, `supplier_id`, `item_id`, and `source_sha256`. Confirmation
revalidates source/context/policy and expiry, applies ERP mutex and proposal
CAS, and persists atomically. This is static source applicability only:
execution count is zero and no test, HTTP, browser, database, or session proof
was obtained.

Its write semantics are strictly `SupplierInvoiceRegistration`, `Event`, and
the resulting receipt. It does **not** post AP or ledger entries, move stock,
pay an invoice, mutate the source document, or create CRM records. Thus S2 is
not evidence for broad S1/S3 operations and must not be folded into the
generic three-case owner exception.

## Future isolated-environment specification — not created

This is a proposal for a later owner decision, not a setup instruction:

- root location: `D:/3/BOSDev/qa-runs/b30-12/<immutable-run-id>/`;
- engine and DB filename: owner must choose exactly one (`SQLite` with
  `b30_12_<run-id>.sqlite3`, or an explicitly provisioned PostgreSQL database);
- media root: `media-<run-id>/`, owned by the isolated root and absent before
  launch; marker: `B30_12_ISOLATED_RUN.json` created exclusively before any
  writer and pinning candidate, engine, DB, media, allowlist and owner-data
  exclusion;
- preflight: candidate commit/hash, empty DB/media, marker/output absence,
  declared fixture manifest, role, routes, command/service symbols, and exact
  write allowlist must all match; otherwise stop before setup;
- permitted future writes must be individually named from the approved case;
  unlisted ERP/CRM writes, owner-local paths, canonical source/index, secrets,
  and network side effects stop the run;
- evidence: immutable before/after synthetic manifest, raw command/stdout/
  stderr, receipt IDs, UAH/unit reconciliation, completed-step reload/relogin
  result and independent-review artifact;
- retention: preserve DB/media/evidence by default; deletion is a separate
  owner decision, never cleanup-on-success.

If an S2 run is ever considered, it must have its own exact authorisation and
fixture review: CEO role, all f55 blob pins, a synthetic supported one-line
document, and write allowlist limited to `ActionProposal`,
`SupplierInvoiceRegistration`, and `Event`. Its oracle must record the read
schema and final receipt fields, exactly one registration/event, and stable
replay. Reload/relogin is explicitly pending a separate feasibility review.

## Historical ledger and stop rules

| Ledger item | State | Rule |
|---|---|---|
| fixture | 3/3 exhausted; final correction static-only | no fourth attempt |
| training progress | 3/3 history | no retry |
| Node exception | 1/1 consumed | no repeat |
| network/payment | 3/3 timeout cause open | separate SAME-PROBLEM exception required |
| full/PG/E2E/browser/lifecycle | no general authorization | do not start from this scope |
| P05/A09/A10/A11 | retained limits | do not infer waiver |

Stop immediately on a pin mismatch, non-empty synthetic target, first
unexpected write path, unavailable isolation guarantee, receipt mismatch, or
any request to touch owner-local data. Preserve raw stdout/stderr, command
arguments, receipts and before/after manifest; no automatic retry.

## Exact future owner-exception question

May root run **one** named, isolated synthetic B30-12 trace against exact
`f55a15de4006d10c0d7c65f8a2ca8499fbb99819` only after separately deciding
whether S1/S3 are eligible and whether the already mapped S2 supplier-invoice
path receives its own exact exception? Any S2 exception must name its CEO
fixture, f55 blob pins, routes/command, `ActionProposal`/
`SupplierInvoiceRegistration`/`Event` allowlist, receipt/replay oracle,
database engine, retention disposition and infrastructure-only rerun rule.

Without an affirmative exact answer, next action is a reviewer check of this
scope document only.
