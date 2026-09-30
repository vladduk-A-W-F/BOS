# BoS 3.0 fixture: навчальна фабрика метизів

`bos3-fasteners-uk-v1` is an isolated synthetic fixture. It is not an upgrade of
the v18 review database, an import of customer data, or evidence of production
readiness. Every company, employee, document and amount in it is fictional.

## Installation boundary

The seed command is deliberately fail-closed. It may run only when all of the
following are true:

- `BOS_DATA_MODE=demo`;
- `BOS3_TRAINING_ENABLED=1` and `BOS3_TRAINING_PROFILE=isolated-synthetic`;
- `BOS3_TRAINING_DB_MARKER=bos3-fasteners-uk-v1` exactly, while the new SQLite
  filename contains `bos3-fasteners`;
- `BOS3_TRAINING_OWNER_USERNAME` exactly equals `--owner-username` and names an
  existing active user;
- `BOS3_TRAINING_INSTALLATION_ID` is nonempty;
- the target has no business rows and no legacy dataset marker.

The command rejects `online-review`, `review.sqlite`, `BoS_Demo.sqlite`,
`BoS_Working.sqlite`, non-SQLite connections and every nonempty target. It never
creates an account or a usable default password. The existing named owner is
bound to the synthetic sales employee; job titles remain presentation data, not
new authorization roles.

Illustrative invocation for the separate owner-managed installation only; this
document does not authorize executing it:

```powershell
$env:BOS3_TRAINING_ENABLED = '1'
$env:BOS3_TRAINING_PROFILE = 'isolated-synthetic'
$env:BOS3_TRAINING_DB_MARKER = 'bos3-fasteners-uk-v1'
$env:BOS3_TRAINING_OWNER_USERNAME = '<existing-owner>'
$env:BOS3_TRAINING_INSTALLATION_ID = '<new-installation-id>'
python manage.py seed_bos3_fasteners --owner-username <existing-owner>
```

## Marker contract

After the one atomic installation, `Configuration["bos3_fixture"]` has these
stable fields. CRM and lesson services must read this marker rather than infer
fixture membership from a display name.

```json
{
  "id": "bos3-fasteners-uk-v1",
  "schema": 1,
  "hash": "SHA-256 of erp/seed/bos3_fasteners_uk_v1.json",
  "synthetic": true,
  "as_of": "2026-09-30",
  "owner_user_id": 0,
  "owner_username": "existing-owner",
  "installation_id": "owner-managed value",
  "db_identity_sha256": "SHA-256 of the resolved SQLite path",
  "source_map": {
    "BOS3-CASE-01": {"order_id": 0, "line_id": 0, "production_id": 0, "purchase_id": 0, "customer_id": 0, "owner_id": 0, "initial": {}, "component_lot_ids": {}, "component_item_ids": {}, "lot_ids": {}},
    "BOS3-CASE-02": {"order_id": 0, "line_id": 0, "customer_id": 0, "owner_id": 0, "approved_lot_id": 0, "blocked_lot_id": 0, "initial": {}},
    "BOS3-CASE-03": {"order_id": 0, "line_id": 0, "customer_id": 0, "owner_id": 0, "invoice_id": 0, "expected": {}}
  }
}
```

The command stores actual generated IDs, never these placeholders. Exact replay
is a no-op only for the same fixture hash, installation ID and owner. A changed
manifest, owner or collision is an error.

## Lesson states

All values are UAH. `as_of=2026-09-30` is an explicit simulated projection date;
it does not change system time. The three historical lesson anchors are stored
separately: 28, 29 and 30 September 2026.

| Case | Initial state | User-operated lesson path |
| --- | --- | --- |
| `BOS3-CASE-01` | 140 approved M10 kits; 400 bolts, 800 nuts and 600 washers on the production location; a planned 120-washer PO; internally confirmed learning plan for production of 360 | Receive -> pending quality -> approve -> reserve -> start -> record the route -> finish with 288.00 UAH labour. Components plus labour yield 12.00 UAH per completed kit. The internal ERP plan confirmation is not a customer promise of a term or delivery. The PO date is a plan, not supplier confirmation or capacity proof. |
| `BOS3-CASE-02` | 250 approved M12 kits in `B3-C2-LOT-A`; 20 blocked kits in `B3-C2-LOT-B` | Reserve only LOT-A, then preview/confirm a 250-kit shipment with `B3-C2-SHP-202`. LOT-B has a clearly labelled unaccepted sample hold form and must remain blocked. |
| `BOS3-CASE-03` | An already shipped order for 800 M10 kits, invoice `B3-C3-INV-303` for 16,400.00 and exactly one 10,000.00 payment | Read the 6,400.00 open balance and create the next contact through the CRM flow. The lesson must not create or replay another payment. |

ERP inventory, purchase, production, reservation, shipment, invoice and payment
effects are built through `erp.service.dispatch` inside one transaction and its
existing write lock. Base branch, synthetic people, counterparties and document
records are fixture prerequisites. Documents contain real UTF-8 sample bytes and
matching SHA-256 values; the blocked LOT-B form is `needs_review`, not accepted
quality evidence.
