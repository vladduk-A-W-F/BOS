# B30-12 · exact-f55 oracle трёх учебных кейсов

## Статус и предел

Это read-only план будущей локальной учебной проверки, подготовленный по
exact candidate `f55a15de4006d10c0d7c65f8a2ca8499fbb99819`. Он не создаёт
`D:/3/BOSDev/qa-runs/b30-12-learning-f55-r1/`, не создаёт SQLite, fixture,
media или marker, не запускает команду, тест, HTTP, browser либо миграцию.
`execution.allowed=false`, `execution.count=0`, автоматический повтор
запрещён. S2 не входит в эти три learning cases; broader MVP S1/S3 не
доказываются этим документом.

Независимый reviewer: `start_overview_review`. Даже после review запуск
требует точного owner exception, включая исторические learning/fixture caps.

## Exact source pins

| Path | f55 git blob | Значение для oracle |
|---|---|---|
| `erp/management/commands/seed_bos3_fasteners.py` | `3b14d16e7f0c5289ce859418c84406a870a135e8` | isolated synthetic fixture, source map и preflight |
| `erp/seed/bos3_fasteners_uk_v1.json` | `ad2b54804a560e6e8b92affdb10b9bfb2859f9df` | fixture ID, synthetic people, counterparties, items и UAH facts |
| `training/access.py` | `d533ee467172fe804215ff23826714d82c619612` | DB/marker/owner identity guard |
| `training/service.py` | `f982fb72e17590dfd6380789f009bfb5ec4a6c86` | case source map, completed-step state и resume semantics |
| `training/test_sessions.py` | `c9e75afc4641830d9e4a849b49d32671c4a0b719` | existing unexecuted server-side operation sequences |
| `erp/urls.py`, `erp/views.py`, `erp/service.py` | `e17a8263e7ebd9a58dd2656b1568a338dfdc5934`, `df0c607e3645ba5bd0e231509a53ab3ca62f4ea7`, `a4b8e1d915c38f4abbe0ecb2aba192475d343c64` | ERP preview and command semantics |
| `operations/urls.py`, `operations/service.py` | `3c0e8bc4f6623f48a82a15a361620a393b01f148`, `64e74153947d47db19cba3bb370d3a078da412d4` | proposal, confirm, receipt, session and replay boundary |
| `crm/commands.py`, `tasks/commands.py` | `d5392bed7d7fc0305c896f62ab987ee1d2ab4a5a`, `3031855111a1906004b0bf628e097520b181e6cd` | C2/C3 handoff and task writes |

The `training/test_sessions.py` sequences are source evidence only. They have
not been run for this candidate by B30-12.

## Future run envelope — proposed, not created

The root-approved intended envelope is SQLite only:

- root: `D:/3/BOSDev/qa-runs/b30-12-learning-f55-r1/`;
- media: `media/`; raw evidence: `evidence/`; marker: `RUN_MANIFEST.json`;
- one named run maximum, preserve every DB/media/evidence artefact, no cleanup
  or reset, no PostgreSQL and no Gate-11 claim.

### Blocking name mismatch

The proposed DB filename `db.sqlite3` is incompatible with the exact learning
guard. `training/access.py:installation()` rejects a basename equal to
`db.sqlite3`; it also requires a basename containing `bos3-fasteners`.
`seed_bos3_fasteners.py:guard_environment()` applies the same substring
requirement. Thus no exact-f55 learning route can start with the specified
`.../db.sqlite3`.

For independent review, the concrete compatible project correction is
`D:/3/BOSDev/qa-runs/b30-12-learning-f55-r1/bos3-fasteners-f55-r1.sqlite3`.
It is a proposed filename only, not a created path or an owner request. The
remaining prescribed environment values are `BOS_DATA_MODE=demo`,
`BOS3_TRAINING_ENABLED=1`, `BOS3_TRAINING_PROFILE=isolated-synthetic`,
`BOS3_TRAINING_DB_MARKER=bos3-fasteners-uk-v1`, a unique installation ID, and
the exact active CEO owner username. The seed guard requires an empty target,
an active named owner, SQLite, and a matching manifest/database identity.

## Common executable-shape oracle

This is the only permitted future command shape after approval:

1. Capture immutable preflight: f55 commit and all source pins; empty target;
   compatible SQLite filename; empty media/evidence roots; exact environment;
   active owner in group `ceo`; fixture manifest SHA; `RUN_MANIFEST.json` with
   the declared allowlist. Stop before setup on any mismatch.
2. Seed exactly `bos3-fasteners-uk-v1` once. It creates the fixture source map
   with runtime PKs; no payload may hard-code those PKs. Bind each payload only
   to the returned marker IDs and preserve the marker verbatim.
3. For each mutation, use one authenticated CEO session: POST
   `/api/erp/preview/` with the listed payload, preserve proposal ID/payload/
   expiry, then POST `/api/operations/confirm/` with that same proposal ID and
   `confirmed=true`. `operations.service` binds a proposal to user, role and
   session, uses a ten-minute expiry, ERP mutex and CAS receipt claim.
4. Preserve every confirmation receipt, `erp_event_id` where produced,
   source-map snapshot, raw request/response metadata, DB/media hashes and
   before/after query evidence. A repeated confirm with the same proposal ID
   must return the literal first receipt; no new business record/event.
5. After each completed learning step, POST the matching
   `/api/training/sessions/<case>/<check>/` action. A fresh authenticated
   session for the same named owner then GETs
   `/api/training/sessions/<case>/`; it must return the same `session_id` and
   completed source-derived step. This is the planned resume oracle. Source
   proves it for a completed answer; source does not yet prove it dynamically
   after every ERP mutation, so each result must be reported as observed rather
   than pre-claimed.

Any mismatch, unexpected path, non-empty target, unknown marker ID, role
change, receipt mismatch, stale proposal, or write beyond the case allowlist
stops the one allowed run. No new ID, seed rerun, reset or retry bypasses a
historical cap.

## Case 01 — supply, receipt and production

**Fixture source state.** `B3-C1-SO-101` is an already confirmed internal
order for 500 M10×80 kits. The initial state is 140 finished kits, a 360-kit
production job `B3-C1-MO-101`, and purchase `B3-C1-PO-101` for 120 washers.
The BOM needs 360 bolts, 720 nuts and 720 washers; 600 washers exist, hence
the exact shortage is 120. All monetary facts are UAH. It is not a customer
delivery promise.

**Role/routes.** CEO only; lesson endpoints use
`/api/training/sessions/BOS3-CASE-01/` and its `start`/`check` actions. ERP
proposal route is `/api/erp/preview/`, confirm route is
`/api/operations/confirm/`.

**Ordered oracle and allowable mutations.** Runtime IDs below come solely
from `Configuration['bos3_fixture'].value.source_map`.

1. Start C1; check `order` with `answers.value=500`, then `supply` with `120`.
   Record session ID and both completed steps.
2. `erp_receive`: `{purchase_id:C1.purchase_id, code:"B3-C1-RCV-101",
   location_id:locations.production, quantity:"120"}`. Expected receipt has
   `lot_id`, code `B3-C1-RCV-101`, quality `pending`; the purchase received
   amount becomes 120. Then `erp_quality` that receipt lot with
   `{result:"approved", inspector_id:people.quality,
   note:"Навчальна перевірка приймання шайб."}`. Check C1 `receipt`.
3. `erp_reserve` four times for C1 `production_id`: bolt lot `360`, nut lot
   `720`, initial washer lot `600`, received washer lot `120`. Each receipt
   must expose `reservation_id` and its stated quantity. `erp_start` with the
   production ID must return status `running`.
4. For every routing row returned by that production job, issue `erp_operator`
   with its exact `operation`, the job owner as `operator_id`, `result:"done"`,
   `minutes:30`, `defects:"0"`, and note `"Навчальна операція виконана."`.
   Exact fixture routing presently has one operation, `Комплектація`; this is
   a checked runtime fact, not a hard-coded assumption.
5. `erp_finish`: `{production_id:C1.production_id, quantity:"360",
   code:"B3-C1-FG-101", location_id:locations.production,
   labor_cost:"288.00"}`. Expected result: a new pending output lot, job
   status `done`, produced `360.000`, actual cost `4320.00`. Approve that lot
   via `erp_quality` with its returned lot ID, `inspector_id=job.owner_id`, and
   note `"Навчальний допуск готових комплектів."`; check C1 `production`.

Expected business writes: `TrainingSession`, `ActionProposal`, `Purchase`
received/status, receipt/output `Lot`, `Movement`, `Inspection`,
`Reservation`, `Production`, `OperatorEntry`, `Event`, and proposal receipts.
No CRM handoff, customer promise, payment, shipping, real supplier document,
or non-fixture data is in this C1 core oracle.

## Case 02 — approved lot, reservation and shipment

**Fixture source state.** `B3-C2-SO-202` is confirmed for 250 kits. Only
`B3-C2-LOT-A` is approved, quantity 250; `B3-C2-LOT-B` is blocked, quantity
20, due to its hold record. `B3-C2-SHP-202` is the required shipment reference.

**Ordered oracle.** CEO starts C2, checks `order=250` and `quality=20`, then:

1. `erp_reserve`: `{lot_id:C2.approved_lot_id, line_id:C2.line_id,
   quantity:"250"}`. Receipt must contain `reservation_id` and `250`.
   Check C2 `reservation`.
2. `erp_ship`: `{line_id:C2.line_id, lot_id:C2.approved_lot_id,
   quantity:"250", reference:"B3-C2-SHP-202"}`. Receipt must preserve line
   ID, `shipped:"250"` and reference. The resulting `Movement(kind=shipment)`
   must reference LOT-A. LOT-B must remain exactly quantity 20 and quality
   `blocked`; reserve/shipment must not mutate it. Check C2 `shipment`.
3. GET `/api/crm/handoff/<C2 session_id>/?case_id=BOS3-CASE-02`. Preserve the
   returned `crm.handoff-draft.v1` payload verbatim; it contains the runtime
   session UUID, source-derived stable handoff hash and typed references. POST
   it unchanged to `/api/operations/preview/`, then confirm. Expected result:
   one C2 `CRMDeal`, linked to that session, with no second shipment/payment.
   Check C2 `crm`, then require case status `completed`.
4. Replay oracle: a second handoff GET returns `existing=true` and creates no
   `ActionProposal`; confirm replay of the same proposal returns its first
   receipt. These are separate from a new CRM update proposal.

Expected writes: `TrainingSession`, `ActionProposal`, `Reservation`, shipment
`Movement`, `SalesLine.shipped`, `Event`, one `CRMDeal`, and receipts. Forbidden:
quality change to LOT-B, another shipment, payment, invoice creation, and any
non-training CRM entity.

## Case 03 — historical invoice/payment, follow-up and CRM

**Fixture source state.** C3 has already shipped 800 kits under
`B3-C3-SHP-303`; invoice `B3-C3-INV-303` is UAH 16,400.00; exactly one
historical payment `B3-C3-PAY-303` is UAH 10,000.00; open balance is UAH
6,400.00. The only CEO-only business work in C3 is a follow-up task and CRM
handoff. It must never invoke `erp_payment`, statement import/reconcile,
invoice creation, reserve, ship or another order action.

**Ordered oracle.** CEO starts C3 and checks `invoice` with `answers.value=6400`.

1. Create the source-bound task through operations preview/confirm:
   `{action:"create_task", title:"Узгодити оплату B3-C3",
   assignee_id:C3.owner_id, deadline:"2026-10-01", order_id:C3.order_id,
   category:"Фінанси", priority:"medium"}`. Expected receipt has
   `state:"succeeded"`, `task_id`, `audit_id`; task is active and its source
   reference is only C3 order. Check C3 `followup`.
2. GET `/api/crm/handoff/<C3 session_id>/?case_id=BOS3-CASE-03`; preserve the
   draft payload unchanged, preview and confirm it. Check C3 `crm`; expected
   case status `completed`, one CRM handoff, and unchanged invoice amount,
   paid amount and open balance.
3. Resume oracle requires a fresh same-owner session GET to retain the same C3
   session and completed invoice/followup/CRM status; stored task/CRM source
   references must still point to C3 order/session. It may not report payment
   settlement merely because a task or CRM record exists.

Expected writes: `TrainingSession`, `ActionProposal`, one `Task`, one task
`AuditEvent`, one `CRMDeal`, and receipts. Forbidden: every ERP financial or
stock mutation, especially a second payment. C3's historical payment is a
fixture fact, never a step to replay.

## Evidence completion and verdict rule

For each case, retain preflight, seed result, source map, every raw request and
response, proposal and receipt, DB/media manifests, and reload/relogin state
responses in the specified evidence root. A case is `PASS_SCOPED` only if all
ordered assertions and preservation assertions are observed in the one
approved run. Any non-run result remains
`SOURCE_MAPPED_DYNAMIC_EVIDENCE_UNCONFIRMED`; it cannot advance full MVP,
browser/E2E, PostgreSQL, payment-network or hosting gates.
