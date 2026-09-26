# REVIEW-BRANCH-RECONCILE

Пріоритет P1. Власник `bos_architect`. Статус **RESOLVED_SOURCE_SCOPED_EVIDENCE_REMAINS**. Автоматичне виконання заборонене чинним `FREEZE_FOR_OWNER_REVIEW`.

## Проблема та історичний доказ

У checkpoint 21.09.2026 PR1 і PR2 мали sibling migrations `0006`, які окремо додавали `Location.branch`. Це створювало ризик повторного DDL та несумісного applied history.

## Що змінилося

У [`26f67e3`](https://github.com/vladduk-A-W-F/BOS/commit/26f67e3822121a0edb69f769290a7d2408f1c8b9) реалізовано frozen bridge `SharedLocationBranch` та fail-closed `AssertCompositionEntry`; `0008_compose_branch_network` зводить обидві історії. [`19601f1`](https://github.com/vladduk-A-W-F/BOS/commit/19601f11aeb543cb5227b918fbeb912375a21d63) виправляє database alias історичної migration. `SalesOrder.branch` і `fulfillment_location` залишені різними поняттями.

## Приймання

Підтверджено source reconciliation і фактичний локальний SQLite update на product `207c7426bcd057cc1a5cfcf172d4c040b05221e9`, runtime `77e8ca05b58efc99d47ce8dd2887074b3c93ba6eaff863a24307ae0e89dc622a`: шість migration nodes, збереження 230 старих rows у 53 nonappend tables. Fresh/local/network fixtures використовують оригінальні SHA-pinned histories і не підробляють receipts.

Це **не** PostgreSQL/full migration acceptance: owned runner працює лише з SQLite, PostgreSQL catalog check має mock cursor. Поточні 11 gates не закриті.

## Наступний крок

Не виконувати новий прогін. Після окремого рішення власника можна лише імпортувати наявні raw logs/manifests/reviews для synthetic histories у переносний evidence package з SHA-прив’язкою. Дозволені файли: `docs/orchestration/evidence/**`, відповідний індекс та звіт; product/migrations/AGENTS не змінювати цією карткою.
