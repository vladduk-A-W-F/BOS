# BROCHURE-MONITOR · offline visual QA staging

This directory is intentionally separate from the earlier light-entry visual
evidence. It contains a new, narrow **BROCHURE-MONITOR** harness only; it does
not rerun or extend prior entry, ERP, CRM, task, progress, payment, network,
E2E, browser, PostgreSQL, full-suite, or column acceptance.

The planned harness loads the candidate's compiled HTML and browser assets from
disk through a fully intercepted `https://bos3.qa` Playwright origin. It starts
no server, connects to no live host, writes only to a fresh child of this
staging directory, serves explicit in-memory GET fixtures, returns `405` for
every non-GET API request, and fails on every unregistered GET.

## Frozen candidate prerequisites

The supplied component contract is `BosOnlineBrochure({content,onExplore,onSignIn})`
with `.bos-online-brochure`, and `BosGlobalMonitor` with
`.bos-monitor[aria-label="Загальний моніторинг"]` and `.bos-monitor-cards`.
The current base `32acfb6` does not yet contain those components, their final
control labels, or the associated CSS. Until that source is staged and checked,
`brochure-monitor-qa.cjs` supports `--plan` only and refuses rendering.

The monitor fixture will satisfy the existing full `homeSnapshotShape` contract
in `frontend/boss_app_source.html`, rather than using a short dashboard object.
It will separately exercise a non-financial role, where money is absent from
the rendered monitor.

## Planned evidence

At most eight screenshots, with required visible anchors and normal-state
checks on each:

1. Desktop brochure cover and first spread before entry.
2. Desktop page turn and bounded previous/next controls.
3. Mobile brochure surface with bounded height and no horizontal overflow.
4. Deep-linked selected case is retained through brochure navigation.
5. Case CTA preserves the selected case; sign-in scroll reveals the actual
   login form without a mutation.
6. Desktop persistent monitor fed by a full valid, fresh BoSHome snapshot.
7. Monitor error/refresh clearing and persistence after safe GET-only ERP then
   CRM navigation, recorded with the two successful route assertions.
8. Mobile monitor plus non-financial role, proving money is not exposed.

Assertions include keyboard previous/next bounds, optional pointer swipe only
if the product exposes it, reduced-motion state, absence of visible alerts and
the ErrorBoundary, console/page errors, monitor loading/error/refresh states
through GET-only fixtures, and document/main overflow. Snapshot values may be
shown only in the existing `fresh` or `empty` states: loading, error, denied,
and stale presentations must render `—`; synthetic 401/403 responses must
clear formerly accepted values.

No browser run is authorized until the product source is frozen and an
independent reviewer accepts the exact fixture, selector, and assertion set.
