# BATCH-02 / N2 · результат адресного erp_adjust

20.09.2026. Кандидат реалізації готовий до independent code review; інтеграцію виконує root. Базовий runtime `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20`; канонічне дерево виконавцем не змінювалося. Працювали лише `execution/batch02/n2/source` і synthetic DB/media.

## Зміна

Новий `erp/adjustment_proposals.py` видає scoped context лише для server-side ERP preview дії erp_adjust. Dependency digest включає повні target Lot/Item/Location, необмежені набори Reservation і Movement цього lot, linked documents, same-code version membership, фактичні verified bytes і актуальний access_revision. Preview та confirm використовують спільний lot-only impact зі старими правилами відображення. Після dispatch і до commit звіряються початкові expected effect/impact та актуальні права; відмінність відкочує всю транзакцію.

Одна additive nullable JSON колонка `ActionProposal.dependency_context` і migration0007 зберігають первісний global fingerprint, payload та receipt CAS. Старі proposals/generic operations-preview мають null context і стару global перевірку. Новий невідомий/некоректний context відхиляється, джерело поточного стану ніколи не стає первісним token. Invalid source bytes у вже scoped proposal не переводять його в global. До видачі proposal початкові unverifiable bytes зберігають legacy preview поведінку. Replay лишається після current Policy і перед state/expiry check, без повторного бізнес-ефекту.

Чинні dispatch/move, mutex, Policy, frontend, інші дії й existing tests не змінено. Runtime performance не вимірювалася; global token все ще обчислюється при створенні scoped proposal, тому жодного прискорення fingerprint не заявлено.

## Фактичні перевірки

| Процес | Результат | Scope |
|---|---|---|
| Baseline red | exit1, 1 метод, 6.253s wall | На незміненому продукті confirm A після незалежного B отримує409 замість200; ні import, ні fixture failure |
| Green attempt1 | exit1, 19 методів, 25.562s wall | 18 PASS; archive test fixture намагався створити одразу archived Employee, штатний ArchiveModel відмовив. Умови product tests не послаблено |
| Green targeted2 | exit0, 3 методи, 8.855s wall | Виправлений fixture через create→audited archive; нові real private-file byte corruption та access change after dispatch обидва PASS |
| AST static parse | PASS | Усі шість файлів allowlist; не замінює runtime |
| PostgreSQL16 concurrency | NOT RUN локально | Три конкретні тести передані root для нової focused CI-картки |

Разом є PASS для **21 різного portable test method** у двох збережених candidate runs; це не твердження про один чистий прогін21/21. Product code між candidate runs не змінювався; змінилися лише новий test fixture/guards і додалися два meaningful tests. Усі старі/помилкові raw outputs збережені. Stage labels/команди/timing/exit/raw SHA є в report.json поряд із raw.log. Додаткова міграція фактично застосована тільки до disposable SQLite Django-test DB, після завершення та БД видалена runner-ом.

21 portable method охоплює справжні CSRF HTTP preview/confirm двох users/sessions, незалежні й спільні lots, reservation membership insert/update/delete/same-sum, target metadata/movements, document version/access/status/checksum/actual BLOB та private-file bytes, missing→present, expiry/session/role/permission/archive, legacy/global fallback, payload/context tampering, replay, post-lock identity, post-preview access, post-dispatch outcome/access rollback, parity повного та lot-only impact на чотирьох fixture states.

## Точні labels наступного дозволеного CI

- `erp.test_adjustment_proposals.AdjustmentProposalTests`:21 portable methods. Цей class придатний для SQLite або PG; setUp звіряє verification_settings та фактичну issued test DB до fixture writes.
- `erp.test_adjustment_proposals.AdjustmentProposalPostgresConcurrencyTests`:3 PG16-only methods. На SQLite навмисно відмовляє, не skip.
- `erp.test_adjustment_proposals` на фактичному PG16:24 methods.

PG tests створюють два реальні окремі connection/backend PID. SQL observer викликає кожну SQL-команду рівно один раз; A реально бере ERP mutex, потім B починає свій UPDATE. Третє реальне monitor connection має побачити pg_blocking_pids(B), що містить PID A, та wait_event_type=Lock, перш ніж дозволити A продовжити. Попередній authored варіант доводив лише SQL-attempt порядок; reviewer виявив цю evidence-прогалину, її виправлено до будь-якого PG запуску. Жоден lock/fingerprint/dispatch не замінюється. Обмеження SET statement_timeout10s, monitor poll≤5s, second-attempt wait≤5s, first-holder wait≤12s, future result20s. Три очікування: різні users/lots200+200; різні users/спільний lot200+409; одна session/proposal replay200+200 з одним Movement/Event. Raw містить N2_POSTGRES_CONCURRENCY JSON із actual version/PIDs/status/trace. Це authored tests, поки не доказ їх проходження.

## Артефакти й межі

`N2_INVENTORY_DESIGN_UA.md` пройшов ACCEPT_SCOPED_DESIGN. `N2.patch`, `CHANGED_SHA256.json`, `SOURCE_MANIFEST.json`, `EVIDENCE_SHA256.json`; raw/report у red, green-attempt1, green-targeted2. Independent final code review pending. Власних external calls/commits/deploy немає. P05 3/3, F04/F05 OPEN, TECHNICAL_READY=false, PILOT_ALLOWED=false незмінні. Немає production migration, full suite, gate3 або E2E повторів.
