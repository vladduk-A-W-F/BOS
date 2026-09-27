# B30-UXD03-DELIVERY-PREP

Static-only preparation for one future ordinary owner-local delivery from the
installed dev4 runtime to an independently reviewed dev5 candidate. This
directory is not a command authorization and must not be used before final
candidate, passport hash, exact allowlist and independent review are present.

## Fixed provenance

- Installed runtime baseline: `e710eb568717dfe3ede945feb899f030bd5ad1ab`
  (`0.3.0-dev.4`).
- Current product evidence commit: `7018cca`.
- Accepted UX source: `a5adcefc8a9bf0ff19f522c585fe7114facd7ee3`.
- Author source commit: `4999f7a`; helper QA was recorded PASS.
- Historical dev4-delivery template reference only:
  `0cdd3ef683433bf8cdccf4a2b559ef7c8b1531a2`; it is not asserted as the
  current canonical source or a dev5 candidate.
- Dev5 candidate commit, passport path/SHA-256, and product allowlist: `PENDING`.

The templates use `None` candidate/passport pins and an empty immutable
allowlist. They reject before capture/apply or a post-start GET until exact
reviewed values replace all pending values together.

## Parameter differences from dev4 delivery

- `maintenance_dev5_delivery.py` accepts only baseline `e710...` and uses the
  isolated `B30-UXD03-DELIVERY` archive/receipt namespace.
- `post_start_dev5.py` expects only `0.3.0-dev.5` after one bounded loopback
  GET of `/`; it has no browser, login, JavaScript, lesson, or API path.
- Both templates retain exact source/manifest/file guards, clean-source and
  prepared binding, protected data/media/credential aggregate, fresh capture
  attestation, process identity, loopback listener, official stop preflight,
  and no-retry refusal behavior.

## Scope and limits

The standing owner policy covers ordinary independently reviewed owner-local
updates; the templates still cannot grant or broaden scope. They exclude
init, seed, migrate, reset, rollback, browser/login, lessons, ERP/CRM writes,
automatic retries, and secret output. The historical `33d7 -> f55` and
`f55 -> e710` windows are consumed and are not repeated by this dev4-to-dev5
preparation. P05/A09/A10/A11 and lifecycle caps remain unchanged.

The required independent reviewer is `start_overview_review`; root performs
any later final-pin review and actual maintenance. HTTP execution count is `0`.
