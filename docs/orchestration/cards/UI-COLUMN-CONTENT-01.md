# UI-COLUMN-CONTENT-01

## Problem and scope

The current module views have ambiguous quantity headers, an unexplained placeholder for missing values, and repeat the heading field in record facts. The owner requested useful column text without duplicated content on 26 September 2026.

Keep semantic facts distinct: identical item and customer strings do not identify the same field. Cards label them separately. Omit only the field already shown as the record heading. Missing dates read `Не встановлено`; other missing values read `Не вказано`. Preserve zero values, decimal money formatting, unknown enums, visibility and command policy.

Metadata labels: `На складі`, `Доступно для операцій`, `Ще прийняти`, `Рядки до виконання`. No API keys, values, business logic, database schema or dependencies change.

## Ownership and allowlist

Source author: columns_implementation, isolated bos-column-content checkout. Independent QA: columns_qa. Independent reviewer: plan_review. Canonical integration: root only.

- frontend/boss_app_source.html
- erp/module_registry.py
- scripts/checks/fixtures/module_catalog/{ceo,manager,observer}.json
- scripts/checks/module_column_content.cjs (new focused harness)
- frontend/boss_app_html.html and assets/app.js (existing build output only)
- docs/orchestration/evidence/current-20260926/columns/ and this card

## Verification boundary

The new focused renderer test, existing controlled module_views, lexical frontend check, existing frontend build, and isolated synthetic desktop/mobile component render are allowed. This is not an app, database, HTTP, full browser acceptance or PG/E2E rerun. Historical P05/Network limits remain unchanged.

The first two harness invocations both failed with zero cards because the fixture lacked the required source.rows descriptor. The state mock was also made faithful to lazy initialization during correction, but it is not established as the cause of either failure. The final fixture clones the real orders descriptor without relaxing product guards or assertions. Three focused invocations were used; raw outputs and source hashes are authoritative.

Acceptance requires independent source/evidence review. A pass is scoped only to column content and this rendering change, not all product readiness gates.
