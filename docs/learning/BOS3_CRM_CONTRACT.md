# BoS 3.0 · CRM contract

Status: implementation contract for the synthetic BoS 3.0 training fixture.

The CRM record is created only after the user confirms a preview through the
existing `POST /api/operations/preview/` and `POST /api/operations/confirm/`
flow. A browser transition, case view, tour step and draft read do not create a
CRM record.

## Read API

- `GET /api/crm/` returns CRM deals visible to the authenticated role.
- `GET /api/crm/deals/<id>/` returns the scoped deal card and its activities.
- `GET /api/crm/handoff/<training_public_uuid>/?case_id=BOS3-CASE-01` returns a
  synthetic, editable handoff draft. Omitting `case_id` uses the session case.
  If the stable handoff already exists, it returns the existing card instead of
  a new draft.

Every endpoint requires authenticated policy identity plus a server-confirmed
training fixture. List and detail reads are centrally restricted to
TrainingSession records with the current user, role, installation ID, fixture
ID and fixture hash; a handoff also requires its session UUID. A URL UUID,
local storage key or client-provided fixture ID alone does not grant access.

## Preview payloads

`crm_handoff` is the only way to create a deal. Required fields are
`training_session_id`, `case_id`, `stable_handoff_hash`, `counterparty_id`,
`owner_id`, `order_id`, `title`, `next_action` and `stage`; case 03 also has
`invoice_id`. IDs must equal the current fixture `source_map` for the session
case. The server computes and verifies `stable_handoff_hash`.

`crm_deal_update` changes a currently visible deal, carries `deal_id`, `reason`
and one or more permitted fields. Stages are forward-only:
`qualification -> supply -> fulfillment -> collection -> won|lost`.

`crm_activity_update` creates an activity with `deal_id`, `owner_id`, `kind`,
`summary` and `status`, or updates one with `activity_id`, `reason` and changed
fields. Kinds are `note`, `call`, `meeting`, `follow_up`; statuses are
`planned`, `done`, `cancelled`.

Optional contact emails must use `.invalid`. The module never sends email,
records payment, creates a counterparty/order/invoice, or accepts arbitrary
URLs.

## Visibility and receipts

CEO can read the installation's training CRM. A manager sees only their owned
or assigned deal with readable order sources, and can create a handoff only
when the fixture source owner is their linked employee. An observer is read-only
and has no implicit visibility outside that scope. Every stored receipt is projected
again at read time, verifies current deal/activity scope, and omits contact
details and unrestricted payloads.
