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

## Требования, existing evidence и gap

| Scope | Existing code/evidence | Current gap | Future oracle/reviewer |
|---|---|---|---|
| S1 order → reserve/shipment → invoice/payment | B30 supply/quality/payment preview, historical scoped server evidence | current exact candidate lacks an end-to-end trace and receipt reconciliation | candidate-bound trace oracle; `start_overview_review` |
| S2 document → draft → reconcile → confirm | accepted S2 backend, controlled ten-case JSX evidence, chain records | current B30 mapping is missing; existing controlled JSX is not browser/backend workflow proof | mapping oracle first; then a separate scope decision |
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
   confirmation; require source identity, proposal/receipt identity and
   reload/relogin preservation of completed confirmation.
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
- CRM: only a case-linked proposal/confirmation where S2 explicitly includes it.

Owner data, media, credentials, local runtime database, secrets and canonical
working tree are preservation targets and may not be read for values, reset,
seeded, migrated, or written. Teardown is not implicit; retention/deletion is
a later owner decision.

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
`f55a15de4006d10c0d7c65f8a2ca8499fbb99819`, with a pre-reviewed manifest,
three specified S1/S2/S3 cases, declared ERP/CRM writes, one raw-evidence
directory, and no access to owner-local DB/media/credentials? This must state
the chosen database engine, cleanup/retention disposition and whether a single
re-run is allowed after an infrastructure-only failure.

Without an affirmative exact answer, next action is a reviewer check of this
scope document only.
