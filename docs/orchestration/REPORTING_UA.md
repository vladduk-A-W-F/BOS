# Авторська звітність і незалежний контроль

20.09.2026. Власник прямо доручив окремий відділ дизайну й звіт кожного відповідального контролеру. Root розподіляє продуктову роботу; контролер перевіряє виконання. Сам звіт або квитанція доставки не замінює source, артефакти чи незалежний review.

Головний: `01a0be90-e790-7351-a8ac-059d523941c4`. Контролер: `01a0bf0f-a9e4-7631-87e1-bb1aed03f174`. Локальний порядок: `D:/3/BOSDev/plans/DESIGN_AND_REPORTING_RU.md`; шаблон: `D:/3/BOSDev/reports/REPORT_TEMPLATE.json`, schema `bos.department-report.v1`.

## Власники й каталоги

| Власник | Напрям | Власний каталог звітів |
|---|---|---|
| root | ORCHESTRATION | `D:/3/BOSDev/reports/root/` |
| `/root/product_integration_continuation` | ENGINEERING | `D:/3/BOSDev/reports/product_integration/` |
| `/root/browser_evidence_check` | DATA_MODEL_REVIEW | `D:/3/BOSDev/reports/migration_composition/` |
| `/root/document_server_adapter`, незалежний reviewer; finance/UI review завершено за повідомленням root | INDEPENDENT_REVIEW | `D:/3/BOSDev/reports/independent_review/` |
| `bos_ux`, постійний чат «БОС — отдел дизайна», `01a0bffa-3fc7-7bc2-9868-86164c6e0315` | DESIGN | `D:/3/BOSDev/reports/design/` |
| Оригінальний execution writer, задача `01a0be9f-b413-7822-9f93-16ba69f4f00f` | DOCS_COORDINATION | `D:/3/BOSDev/reports/execution_writer/` |

Постійний чат дизайну і завершений незалежний reviewer — різні власники. Початкове призначення audit для `/root/document_server_adapter` замінене: він передає лише partial handoff і не веде паралельний audit. У звітах зберігати фактичне авторство. Designer не стає незалежним reviewer власного результату. Фактичний ID чату підтверджено у `C:/Users/user/AppData/Local/BOSDev/design-thread-creation.json` (`CREATED_VERIFIED`, verified_at `2026-09-20T18:05:47.677284+00:00`); його worktree — `C:/Users/user/.codex/worktrees/c8b3/repo`. Не використовувати `clientThreadId` як thread ID.

## Коли і що звітувати

Звіт потрібен при отриманні призначення, значущому перевіреному результаті, передачі на review та реальному блокері. Після завершення вказати наступну отриману картку або `executor_available=true`. Незмінений статус за таймером і відповіді-ехо на квитанції не надсилати.

Кожен власник атомарно записує окремий JSON за шаблоном у свій каталог. Обов'язкові поля шаблону: schema, report_id, reported_at_utc, author_thread_id, owner, department, card_id, source_commit, dependencies, worktree, allowlist, status, result, artifacts, checks, independent_review, blocker, next_step, executor_available; `template_only=false`. Для кожного артефакту — точний шлях/SHA, для виконаної команди — exit code й scope. Для невиконаної перевірки — NOT RUN; skipped CI не PASS. Авторство та час UTC не підмінювати.

Звіт відокремлює: що виконав автор, які результати інших він лише індексував, що прийняв незалежний reviewer і що повідомив координатор. Публікація, source snapshot і готовність продукту — різні факти. Історичні докази залишаються на своїх hashes, а новий source не успадковує PASS автоматично. Паролів, секретів, приватних payload і реальних клієнтських даних у звітах немає.

Вбудований subagent без каналу відправки зберігає свій авторський JSON. Root передає його незміненим одним повідомленням із посиланням та ім'ям автора; report_id залишається стабільним. Зведення root про розподіл роботи доповнює, а не підмінює звіти виконавців.

## Єдиний канал передачі контролеру

Root і зовнішній execution writer передають повідомлення з посиланням на JSON тільки так, зі своїм реальним `CODEX_THREAD_ID`. Окремий дизайн-чат також має пряму авторизацію на цей канал у власному початковому призначенні:

```powershell
& 'D:/3/BOSDev/venv/Scripts/python.exe' -B 'C:/Users/user/AppData/Local/BOSDev/tools/codex_channel.py' send --target observer --message-file '<власний MESSAGE.md>' --message-id '<стабільний ID одного звіту>'
```

Повідомлення має містити source, allowlist, evidence, verdict і наступний крок або посилання на JSON із цими полями. Один стабільний ID відповідає одному звіту. Self-send, невідомі адресати, дублювання та прямий обхід журналу заборонені. При невизначеній доставці не повторювати автоматично; зберегти матеріал і явно зазначити блокер доставки. Квитанція ACKNOWLEDGED означає доставку, а не приймання роботи.

Для першого звіту дизайну точні параметри вже призначені: message-file `D:/3/BOSDev/reports/design/INITIAL_REPORT_MESSAGE.md`, message-id `design-initial-report-20260920`; JSON `D:/3/BOSDev/reports/design/INITIAL_REPORT.json`. Цей ID належить дизайнеру; інші автори не повторюють його від свого імені. Подальші окремі звіти мають власні стабільні ID та дозволені шляхи.

Перший авторський пакет уже має статус PREPARATION_READY_FOR_INDEPENDENT_REVIEW і повідомляє про19 PNG; independent_review залишається pending. Не повторювати первісну відправку або audit заради організаційної картки. Root призначає незалежну перевірку окремо. У поточному codex_channel.py alias `design` веде до фактичного ID `01a0bffa-3fc7-7bc2-9868-86164c6e0315` для призначень від головного; звіти всіх власників, включно дизайнером, ідуть до `observer` через той самий журнал.

В `observer.json` пише лише контролер під `bos_dev.state_lock`. Власники не редагують чужі звіти. Чинний heartbeat залишається один і без змін; цей порядок не створює нового розкладу, сервісу чи додаткової моделі.

## Поточний checkpoint і обмеження

Організаційний пакет підготовлено на чистому `620aeab2010c6c8327ce46c25bb62435bcf7f9e4`; факт публікації цього checkpoint у PR1 підтверджений головним. Продукт прийнятих screenshots — `646d3b80597e087a1ada14221024ec40588996f0`, source `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`. Старі спостереження `3d979060` і browser-attempt4 FAIL не переписуються. Цей docs/config patch не приймає pending network-код, нові PG результати або майбутній merge.

Зберігаються 35 наявних queue IDs, усі 11 вимог, `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, P05 3/3, A09/A10/старий A11, ERP mutex і зовнішня reservation. Постійний чат дизайну має першу [PLAN-UX](../design/PLAN_UX_INCREMENT_UA.md); цей документ не засвідчує її виконаний audit або незалежне приймання.
