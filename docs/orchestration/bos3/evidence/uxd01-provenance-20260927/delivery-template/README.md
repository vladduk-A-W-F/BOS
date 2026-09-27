# B30-UXD01-DELIVERY-PREP

Static-only preparation for one future ordinary owner-local delivery from the
installed dev5 runtime to an independently reviewed dev6 candidate. This
directory is not a command authorization and must not be used before final
candidate, passport hash, exact allowlist and independent review are present.

## Fixed provenance

- Installed runtime baseline: `3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c`
  (`0.3.0-dev.5`).
- Assigned source reference for static preparation: canonical `c1a36a6` plus
  the assigned CONTROL card. It is not asserted as a dev6 candidate.
- The accepted dev5 delivery template is a historical implementation reference
  only; it does not provide a current candidate or pin for this card.
- Dev6 candidate commit, passport path/SHA-256, and product allowlist: `PENDING`.

The templates use `None` candidate/passport pins and an empty immutable
allowlist. They reject before capture/apply or a post-start GET until exact
reviewed values replace all pending values together.

## Parameter differences from dev5 delivery

- `maintenance_dev6_delivery.py` accepts only baseline `3d1e...` and uses the
  isolated `B30-UXD01-DELIVERY` archive/receipt namespace.
- `post_start_dev6.py` expects only `0.3.0-dev.6` after one bounded loopback
  GET of `/`; it has no browser, login, JavaScript, lesson, or API path.
- Both templates retain exact source/manifest/file guards, clean-source and
  prepared binding, protected data/media/credential aggregate, fresh capture
  attestation, process identity, loopback listener, official stop preflight,
  and no-retry refusal behavior. The template cannot pass capture or apply
  while its candidate, manifest, and exact allowlist remain pending.

## Scope and limits

The standing owner policy covers ordinary independently reviewed owner-local
updates; the templates still cannot grant or broaden scope. They exclude
init, seed, migrate, reset, rollback, browser/login, lessons, ERP/CRM writes,
automatic retries, and secret output. This is a new future candidate window,
not a repeat of the consumed dev5 delivery window. P05/A09/A10/A11 and
lifecycle caps remain unchanged.

The required independent reviewer is `start_overview_review`; root performs
any later final-pin review and actual maintenance. HTTP execution count is `0`;
no maintenance, lifecycle, HTTP, browser, or runtime operation has occurred.
