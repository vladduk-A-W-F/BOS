# BoS v17: текущий цикл и ручная проверка

Статус: **FREEZE_FOR_OWNER_REVIEW**. Это отчёт о текущем согласованном цикле; полное завершение MVP, техническая готовность и разрешение пилота не заявляются.

Membership UI actual3: **FAIL overall (7 PASS / 1 FAIL / 0 NOT_RUN)**. Private v5 только статически принят, не применён, behavior NOT_RUN. S2 имеет scoped backend/control/service evidence; полное текущее UI/runtime принятие продукта не установлено.

Продуктовый commit: `207c7426bcd057cc1a5cfcf172d4c040b05221e9`. Runtime SHA-256: `77e8ca05b58efc99d47ce8dd2887074b3c93ba6eaff863a24307ae0e89dc622a`. Сборка `assets/app.js`: `4b2918a018cf2499a4aa2ea8ca598c7abfd17fd74379ab4236250723a5390263`.

Локальная ветка: `codex/network-composition-20260920`. Ветка публикации Git: `setup/bos-gpt-orchestration-20260920`. [Draft PR #1](https://github.com/vladduk-A-W-F/BOS/pull/1). Изменения не слиты в main. Документационный commit определяется как Git commit, содержащий этот отчёт; точный итоговый pushed SHA и CI находятся в финальном внешнем receipt.

Настроенный локальный адрес: [BoS на этом компьютере](http://127.0.0.1:8876/). Датированное состояние: **HISTORICAL_UPDATE_ACCEPTED_LATER_OUTAGE_RECOVERY_OWNED_BY_CONTROLLER**, наблюдение `2026-09-21T21:27:13.1597409Z`; браузер: **PASS_SCOPED_4_OF_4_HISTORICAL_AT_2053UTC**. Проверка браузера фиксирует состояние в указанное в receipt время. Эта запись не является текущей проверкой доступности; результат восстановления и окончательная ссылка находятся в датированном внешнем итоговом отчёте.

Временный онлайн-доступ: **PRIOR_TEMP_URL_OUTAGE_RESTORATION_PENDING_CONTROLLER_RECEIPT**. Транспорт к существующему стенду ведёт контролёр отдельно; фактическая ссылка или точный blocker отражаются во внешнем итоговом отчёте. Это не изменение продуктового source и не production acceptance.

Учётные данные сохраняются в DPAPI. Получить их на компьютере стенда можно через [исходный show-login.ps1](D:/3/Codex/2026-09-20/bos-execution/work/continuation-focus-frozen-20260920/local-review-support/show-login.ps1). Открыть PowerShell и выполнить:

```powershell
& 'D:/3/Codex/2026-09-20/bos-execution/work/continuation-focus-frozen-20260920/local-review-support/show-login.ps1'
```

Пароли не включены в Git, чат и отчёт.

## Что включено

В принятом source207c находятся сетевая композиция, источники заказа и расчётов, регистрация поддержанного документа поставщика, базовая передача Task между отделами, компактная навигация, явно ручные/неизмеренные KPI и чтение каталога отделов. Это сохраняет существующий command/service путь с preview/confirm. Новая private очередь и membership UI/backend union не применены.

## Сверка 35 карточек

READY_SCOPED означает готовность ровно указанной карточки в исторически принятом scope. Это не новый полный прогон на 207c. Статусы старых evidence сохранены, остаточные действия не являются автоматической очередью.

| Статус | Количество |
|---|---|
| READY_SCOPED | 24 |
| PARTIAL | 6 |
| BLOCKED | 4 |
| NOT_STARTED | 1 |

| Карточка | Статус | Выполнено и доказательство | Осталось |
|---|---|---|---|
| P10-003 — P06-F02: backend-aware isolation guard | READY_SCOPED | Исправлен backend-aware guard изоляции InitialImportFixture; исторический scoped SQLite/PG16 PASS. [BATCH_01_UA.md](BATCH_01_UA.md) | Полный актуальный P06 не принят; исходную БД не использовать как тестовую. |
| PLAN-N1 — Звірити max_length та валідацію фактичних входів | PARTIAL | Проверены и исправлены входы REQUEST/SHIP относительно max_length. [BATCH_01_UA.md](BATCH_01_UA.md) | Остальные фактические входы требуют отдельного завершения карты валидации. |
| PLAN-F03 — Валідні invoice-коди у concurrency fixtures | READY_SCOPED | В concurrency fixtures разделены валидные invoice-коды и негативные проверки длины. [BATCH_01_UA.md](BATCH_01_UA.md) | Полная конкурентная проверка всех денежных и складских действий остаётся открыта. |
| PLAN-F06 — Повнота E2E evidence та SHA-індекс | READY_SCOPED | Completeness check и SHA-индекс E2E artifacts приняты на unit-проверках. [BATCH_01_UA.md](BATCH_01_UA.md) | Полный E2E с новым источником и полным архивом не выполнен. |
| PLAN-TIME — Причини тайм-аутів P06-F04/F05 | BLOCKED | Ограниченная диагностика F04/F05 выполнена, исходные receipts сохранены. [PLAN_TIME_RESULTS_UA.md](PLAN_TIME_RESULTS_UA.md) | Причина тайм-аутов не доказана; runtime fix не применён. Исчерпанные suites не повторять автоматически. |
| PLAN-N2 — Замір fingerprint та ADR конкурентності | PARTIAL | Измерен глобальный fingerprint; адресная зависимость реализована для erp_adjust. [BATCH_02_UA.md](BATCH_02_UA.md) | Остальные действия сохраняют global fallback; механизм не считается повсеместно внедрённым. |
| PLAN-SOURCE — P04-F01: міжплатформний source SHA | READY_SCOPED | Межплатформный runtime digest и native Windows proof приняты в указанном scope. [WINDOWS_SOURCE_UA.md](WINDOWS_SOURCE_UA.md) | Не заменяет полную проверку чистой Windows-установки. |
| PLAN-LINKS — Gap-map моделі пов’язаних процесів | PARTIAL | Сетевая композиция, trace, S2 registration и связанная synthetic service-цепочка приняты в ограниченном scope. [NETWORK_COMPOSITION_UA.md](NETWORK_COMPOSITION_UA.md) | Остаются общий браузерный маршрут, другие роли, завершение Task с результатом и отдельный restart/reopen. |
| PLAN-UX — Сценарії, комунікація та джерела показників | PARTIAL | Ранее приняты девять UI-контекстов; добавлены links, compact menu, manual KPI и department settings с controlled JSX checks. [NETWORK_COMPOSITION_UA.md](NETWORK_COMPOSITION_UA.md) | Общий текущий UXD-01–08, размеры, native 200%, роли и 28 наблюдений не приняты полностью. |
| PLAN-GPT — Специфікація GPT adapter та рольових evals | PARTIAL | Подготовлен контракт adapter/рольовых evals; продуктовый API выключен. [BATCH_01_UA.md](BATCH_01_UA.md) | Нужны разрешённые поля, модель, бюджет и реализация с проверкой прав; не запускать до новых указаний. |
| PLAN-ACCEPT — Повне технічне приймання P19/P20 | BLOCKED | Собраны scoped evidence и незакрытые условия всех 11 gates. [BATCH_01_UA.md](BATCH_01_UA.md) | Полное техническое принятие отсутствует; P05/A09/A10 и старые A11 границы сохраняются. |
| PLAN-PILOT — Паспорт пілота та умови P22–P24 | BLOCKED | Паспорт пилота подготовлен. [BATCH_01_UA.md](BATCH_01_UA.md) | Нужны выбранная компания, сценарий, данные, критерии и отдельное разрешение владельца после технических условий. |
| PLAN-LINKS-READ — Реалізувати серверний trace одного замовлення | READY_SCOPED | Серверный trace заказа принят scoped на SQLite и PostgreSQL 16. [BATCH_02_UA.md](BATCH_02_UA.md) | Исторический scope не подтверждает все новые браузерные пути и роли. |
| PLAN-UX-TRACE — Додати джерела виконання в чинний inspector | READY_SCOPED | Источники исполнения добавлены в inspector; component acceptance сохранён. [BATCH_02_UA.md](BATCH_02_UA.md) | Полная текущая browser acceptance для всех связей не выполнена. |
| PLAN-N2-ADJUST — Адресна перевірка погодження erp_adjust | READY_SCOPED | Адресное согласование erp_adjust принято на SQLite/PG16, включая отдельные реальные concurrency cases. [BATCH_02_UA.md](BATCH_02_UA.md) | Не распространять результат на остальные command writers. |
| PLAN-SAAS — Пакет SaaS з ізоляцією компаній та onboarding | PARTIAL | Подготовлен пакет отдельной установки на компанию и onboarding. [BATCH_03_UA.md](BATCH_03_UA.md) | Production install, TLS, upgrade/rollback и эксплуатационная готовность не приняты. |
| PLAN-LANDING — Лендинг готового ядра та шлях до демонстрації | READY_SCOPED | Исторически опубликован Sites landing; принято только landing/navigation. [BATCH_04_UA.md](BATCH_04_UA.md) | Это отдельный Site. Его версия не обновлялась текущим Django closeout; не считать его адресом новой ERP. |
| PLAN-CONNECTORS — Контракти підключення систем клієнтів | NOT_STARTED | Есть план контрактов систем клиентов. Нет реализации/evidence | Реализация коннекторов не начата; нужны реальные согласованные системы и данные после новых указаний. |
| PLAN-SOURCE-WINDOWS — Native Windows source SHA proof for the current runtime | READY_SCOPED | Native Windows source SHA proof сохранён с точным историческим источником. [docs/orchestration/evidence/windows-source/report.json](evidence/windows-source/report.json) | Не заменяет gate 11 и нынешние проверки приложения. |
| FRONTEND-GLOBALS — Native browser globals у lexical checker | READY_SCOPED | Native browser globals учтены lexical checker. [VERTICAL_UA_UA.md](VERTICAL_UA_UA.md) | Это проверка checker, не full browser acceptance. |
| BOOTSTRAP-OWNER — Перший керівник порожньої установки | READY_SCOPED | Создание первого CEO пустой установки принято scoped SQLite/PG16. [VERTICAL_UA_UA.md](VERTICAL_UA_UA.md) | При обновлении существующего review-стенда bootstrap и seed не повторяются. |
| VERTICAL-UA-DATA — Філія, склад, замовлення та джерела UAH | READY_SCOPED | Филиал, склад, заказ, UAH и Policy sources реализованы и scoped проверены. [VERTICAL_UA_UA.md](VERTICAL_UA_UA.md) | Новые серверные изменения имеют отдельные доказательства; полный текущий role sweep открыт. |
| VERTICAL-UA-UI — Робочі точки в чинному ERP UI | READY_SCOPED | Рабочие точки встроены в существующий ERP UI; controlled UI acceptance сохранён. [VERTICAL_UA_UA.md](VERTICAL_UA_UA.md) | Текущий four-route smoke не заменяет все responsive/role/business проверки. |
| UI-LOCAL-RUNNER — Новий ізольований локальний browser runner | READY_SCOPED | Собственный локальный browser runner ранее дал 7/7 на точном 646d3b8. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Этот PASS относится к старому источнику; новый smoke учитывается отдельно. |
| LOCAL-GATE1-4 — Порожні міграції й актуальний access sweep | BLOCKED | Историческая PG миграция и статический каталог маршрутов сохранены. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | SQLite original exit не установлен; current access sweep прерван без receipt; full gates 1/4 не приняты. |
| S1-CONFIRM-RECOVERY — Збереження ID погодження та квитанції | READY_SCOPED | Сохранение proposal ID и квитанции реализовано и принято в исходном bounded scope. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Полная цепочка заказа, роли, reload/restart и concurrency остаются частичными. |
| PLAN-DOC-MATCH-CONTRACT — Pure mock-контракт документа | READY_SCOPED | Pure mock-контракт документа принят; позднее добавлена реальная серверная registration. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Поддерживаются согласованные synthetic bytes; OCR и произвольные документы не подтверждены. |
| SUPPLY-OPTIONS-READ — Дозволені джерела забезпечення | READY_SCOPED | Чтение разрешённых источников обеспечения принято SQLite12. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Полный negative role sweep и linked browser flow остаются открыты. |
| FLOW-ORDER-SETTLEMENT — Фінансові джерела конкретного замовлення | READY_SCOPED | Исправлены ссылки финансовых источников заказа; service chain подтверждает 300/120/180 UAH. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Платёж — локальная учётная запись; банковская интеграция и полный browser flow не заявляются. |
| DOC-MATCH-SERVER — Перевірені байти й Policy для mock-сверки | READY_SCOPED | Проверка байтов документа и Policy реализована; registration backend отдельно принят 11 targeted checks. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Обычные неподдержанные документы не превращать в успешное распознавание. |
| FLOW-READ-UI — Маршрути й UI забезпечення та розрахунків | READY_SCOPED | Маршруты обеспечения и расчётов и источники доступны в принятом bounded UI scope. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Проверка всех текущих связей, ролей и возврата контекста не завершена. |
| LOCAL-REVIEW-SUPPORT — Керовані процеси локального synthetic-стенда | READY_SCOPED | Lifecycle support принят отдельно: process ownership, synthetic review data и локальный вход. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Новый результат обновления/запуска указывается отдельно; support acceptance не равна deployment acceptance. |
| DOC-MATCH-READ-UI — Явне зіставлення та оригінальні докази | READY_SCOPED | Явное сопоставление и исходные evidence реализованы; S2 command UI позднее принят controlled10. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Общий текущий browser S2 и multi-role acceptance не выполнены. |
| FLOW-BROWSER-HELPER — Оракул трьох обмежених browser-кроків | READY_SCOPED | Подготовлен и scoped принят oracle трёх ограниченных браузерных шагов. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Helper сам по себе не подтверждает исполнение сценария. |
| WORKPOINT-DIALOG-FOCUS — Повернення фокуса до чинного opener | READY_SCOPED | Возврат фокуса к актуальному opener исправлен и ранее проверен реальным браузером. [CONTINUATION_20260920_UA.md](CONTINUATION_20260920_UA.md) | Исторический browser PASS не заменяет full current-source keyboard/layout проверку. |

## Три бизнес-сценария

| Критерий | Статус и подтверждено | Осталось |
|---|---|---|
| S1: Заказ → обеспечение → отгрузка → расчёты | PARTIAL. Synthetic service chain: reserve/ship 3.000; invoice 300.00, paid 120.00, debt 180.00 UAH; references and history retained. [linked](evidence/closeout-v17/linked.json), [reuse](evidence/closeout-v17/reuse.json), [ui_links](evidence/closeout-v17/ui_links.json) | Текущий общий UI, не-CEO роли, отрицательные случаи, отдельный restart/reopen и complete Task actual result. |
| S2: Документ поставщика → сопоставление → регистрация | PARTIAL. Registration backend 11 targeted PASS; command UI controlled10 PASS; service chain registration 60.00 UAH linked to receipt, quality stays pending. [s2_backend](evidence/closeout-v17/s2_backend.json), [s2_targeted](evidence/closeout-v17/s2_targeted.json), [s2_ui_review](evidence/closeout-v17/s2_ui_review.json), [linked](evidence/closeout-v17/linked.json) | Browser путь целиком и роли не приняты; arbitrary OCR, supplier payable/payment posting не реализованы этим scope. |
| S3: Дефицит → закупка/перемещение → приёмка → качество | PARTIAL. Принята synthetic purchase→receipt→registration→quality→reserve→ship цепочка и ранее bounded transfer UI. [linked](evidence/closeout-v17/linked.json), [reuse](evidence/closeout-v17/reuse.json), [actual6](evidence/closeout-v17/actual6.json) | Полная current browser цепочка, альтернативные пути, реальные права всех ролей и restart не подтверждены. |

## UXD-01–08

| Критерий | Статус и подтверждено | Осталось |
|---|---|---|
| UXD-01: Понятные показатели | PARTIAL. Manual N/100, unmeasured/loading/error/denied neutral states приняты controlled8. [kpi](evidence/closeout-v17/kpi.json) | Не все dashboard метрики имеют подтверждённые формулу, период, источник и актуальность. |
| UXD-02: Показатель → список → запись → источник → назад | PARTIAL. Trace и UI-links controlled12; существующий inspector источников. [ui_links](evidence/closeout-v17/ui_links.json), [linked](evidence/closeout-v17/linked.json) | Общий текущий browser маршрут с фильтрами и возвратом контекста открыт. |
| UXD-03: Рабочая очередь отдела | PARTIAL. Базовый Task/department backend есть; новая private queue controlled8 подготовлена. [task_queue](evidence/closeout-v17/task_queue.json), [linked](evidence/closeout-v17/linked.json) | Новая queue не интегрирована; нет принятого полного пользовательского пути owner/deadline/priority/source. |
| UXD-04: Передача и результат одной задачи | PARTIAL. Service chain сохраняет same Task/source/branch/history при handoff. [linked](evidence/closeout-v17/linked.json) | Оба проверенных actor — CEO; actual result пуст; получатель process/done с результатом в общем UI не проверен. |
| UXD-05: Компактная навигация | PARTIAL. Menu controlled8 принят, menu интегрирован в 37fb57 и сохранён в 207c. [menu](evidence/closeout-v17/menu.json), [source](evidence/closeout-v17/source.json) | Полное real layout/keyboard/200% покрытие нового меню отсутствует. |
| UXD-06: Читаемость и доступность | PARTIAL. Исторический scoped browser 646d3b8: 390/768/1440,200%,keyboard/Escape. [source](evidence/closeout-v17/source.json) | На 207c полного повторного gate10 нет; read-only smoke ограничен 1440 и 4 основными маршрутами. |
| UXD-07: Загрузка, ошибки, права, stale и повторные клики | PARTIAL. Controlled cases KPI/menu/SDC и прежних команд покрывают отдельные состояния. [ui3](evidence/closeout-v17/ui3.json), [v5](evidence/closeout-v17/v5.json), [kpi](evidence/closeout-v17/kpi.json), [source](evidence/closeout-v17/source.json) | UI8 actual3 FAIL: retained preview handler создаёт вторую proposal. Private v5 guard static accepted, behavior NOT_RUN; full 28 наблюдений/5 roles NOT_RUN. |
| UXD-08: Одинаковые факты, роли, суммы и подтверждение | PARTIAL. Точные UAH service facts и scoped preview/confirm сохранены; UI controlled checks приняты по модулям. [linked](evidence/closeout-v17/linked.json), [reuse](evidence/closeout-v17/reuse.json) | Полное multi-role consistency/current HTTP/restart/concurrency не доказано. |

## 11 приёмочных gates

Их определения и замороженный inventory85/12 не изменены. Scoped PASS и локальная review-публикация не закрывают полное приёмочное условие.

| Gate | Текущий статус | Сохранённая граница доказательства |
|---|---|---|
| 1: Міграції на порожніх SQLite і PostgreSQL | NOT_ACCEPTED_CURRENT_207C | Historical e66af PG16 fresh migration exit0; SQLite original exit unknown after observer cleanup error. Current frozen candidate not rerun. |
| 2: 151 функціональна + 5 launcher + решта тестів на обох СУБД | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | Scoped new tests and historical CI do not replace both-DB acceptance. PG new-read preflight made0 test attempts: port55439 unavailable and SQLite-only fixture guard. Separate fixture correction has2 SQLite PASS; not PG PASS. |
| 3: П’ять інваріантів, мінімум 1000 випадкових прогонів кожний | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | Five invariants x1000 not established for this candidate. |
| 4: Права всіх ролей на всіх API/admin та всіх поверхнях даних | NOT_ACCEPTED_CURRENT_207C | Old fixture failed after an actual HTTP422 but before route sweep; current-environment/access-current-1 has checks=[] and no final receipt. Catalogue195/required95 is static, not all-role execution. |
| 5: Два одночасні виклики кожної грошової та складської дії | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | Historical concurrency evidence has older source identity; UI same-ID replay and mocked oracles are not all writers concurrently. |
| 6: Наскрізний процес на чистій базі, звірка до копійки | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | Attempt5 separately accepted transfer/payment UI preview-confirm and same-proposal browser HTTP replay, plus ordinary-document unsupported/no-writes. These3 bounded flows do not establish full business E2E. Exhausted preset not retried. |
| 7: Backup/restore у чисту установку: кількості, суми, версії, SHA | NOT_ACCEPTED_CURRENT_207C | Read-only prerequisite review completed at530043a. Usable Linux amd64 runner, compatible offline wheels, pinned Caddy and OpenSSL remain unproven. Same-N restore NOT RUN; no install/upgrade authority inferred. |
| 8: Чиста виробнича установка: TLS, cookies, proxy, health, logs | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | Production install/TLS/cookies/proxy/logs not accepted. A09 exact13MiB retry remains forbidden. |
| 9: Оновлення N → N+1 та відновлення N після rollback | BLOCKED_OR_INCOMPLETE_NO_AUTOMATIC_REPEAT | A10 activation/upgrade/rollback restriction remains; no new run. |
| 10: Браузер: 390/768/1440, 200%, клавіатура, Escape, мережа | NOT_ACCEPTED_CURRENT_207C | Independent root accepted actual attempt5: exit0,7of7 at646d3b80597e087a1ada14221024ec40588996f0/source98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a.26 artifacts hash/length verified. Exact child8084/launcher12712 exited; source/DB unchanged. Attempt4 focus FAIL at530043a preserved. Does not cover PR2 or future merge. |
| 11: Чиста Windows / Python 3.12: критерії 1–3 і 6 | NOT_ACCEPTED_CURRENT_207C | Windows source/stdlib proofs and Python3.12 runtime do not establish fresh Windows criteria1-3 and6. |

## Проверки, FAIL и NOT_RUN

| Проверка | Результат | Подробности/история |
|---|---|---|
| S2 backend targeted | PASS_SCOPED | {"attempt": 4, "pass": 11, "prior_failures": 3} [s2_targeted](evidence/closeout-v17/s2_targeted.json), [s2_backend](evidence/closeout-v17/s2_backend.json) |
| S2 command UI controlled | PASS_SCOPED | {"attempt": 3, "pass": 10, "history": "attempt1 3 PASS/1 FAIL/6 NOT_RUN; attempt2 4/1/5 retained"} [s2_ui_review](evidence/closeout-v17/s2_ui_review.json) |
| UI links controlled | PASS_SCOPED | {"attempt": 2, "pass": 12, "history": "attempt1 0 PASS/1 FAIL/11 NOT_RUN retained"} [ui_links](evidence/closeout-v17/ui_links.json) |
| Linked synthetic service chain | PASS_SCOPED | {"attempt": 2, "steps": 10, "confirmed_transitions": 12, "history": "First launcher failure retained. No real HTTP/browser, both reopen actors CEO; no Task actual result."} [linked](evidence/closeout-v17/linked.json), [reuse](evidence/closeout-v17/reuse.json) |
| Compact menu controlled | PASS_SCOPED | {"attempt": 3, "pass": 8, "history": "Two prior FAIL retained; real DOM/layout not proven"} [menu](evidence/closeout-v17/menu.json) |
| Manual/unmeasured KPI controlled | PASS_SCOPED | {"attempt": 2, "pass": 8, "history": "First 0 PASS/1 FAIL/7 NOT_RUN retained"} [kpi](evidence/closeout-v17/kpi.json) |
| SDC department settings controlled | PASS_SCOPED | {"attempt": 1, "pass": 10, "not_run": "SDC11 real DOM"} [source](evidence/closeout-v17/source.json) |
| Private Task queue controlled | PASS_SCOPED_PRIVATE_NOT_APPLIED | {"attempt": 1, "pass": 8} [task_queue](evidence/closeout-v17/task_queue.json) |
| Private membership UI | FAIL | {"attempt": 3, "pass": 7, "fail": 1, "not_run": 0, "history": "Actual1 transform failure: 0/0/8; actual2 missing extracted SegmentedControl: 0/1/7; metadata refusals2 do not reset actual3."} [ui3](evidence/closeout-v17/ui3.json) |
| Private membership v5 owner guard | STATIC_ACCEPT_BEHAVIOR_NOT_RUN | {"new_target_invocations": 0, "integrated": false} [v5](evidence/closeout-v17/v5.json) |
| SDC accepted build/package | BUILD_EXIT0_WITH_CAPTURE_LIMITS | {"build_count": 1, "exits": [0, 0, 0, 0], "limitations": "Functions ReferenceError preserved; HOST_CAPTURE_COMPLETE/HOST_MANIFEST absent; exact full capture compliance false. No new build needed for unchanged runtime."} [source](evidence/closeout-v17/source.json) |
| Historical browser focus/responsive | PASS_SCOPED_646D3B8 | {"pass": 7, "source": "646d3b80597e087a1ada14221024ec40588996f0", "limits": "Not 207c full gate10"}  |
| Historical network browser read-only actual6 | PASS_SCOPED | {"pass": 4, "history": "Earlier actual1–5 failure history retained, bounded actual5 subscopes accepted separately"} [actual6](evidence/closeout-v17/actual6.json) |
| Full current MVP UI/roles/restart protocol | NOT_RUN | {"groups": 12, "observations": 28, "roles": 5, "limits": "Prepared scripts/fixtures are not execution or MVP PASS"}  |
| Current review runtime update | HISTORICAL_UPDATE_ACCEPTED_LATER_OUTAGE_RECOVERY_OWNED_BY_CONTROLLER | {"details": {"status": "HISTORICAL_UPDATE_ACCEPTED_LATER_OUTAGE_RECOVERY_OWNED_BY_CONTROLLER", "running": false, "url": "http://127.0.0.1:8876/", "attempt": 2, "migration_count": 6, "seed_count": 0, "build_count": 0, "business_rows_preserved_at_update": 230, "business_tables_preserved_at_update": 53, "preservation_note": "Old-column projections verified at update; later owner activity and ordinary login are not claimed byte-unchanged.", "history": "Actual1 update FAIL before migration; actual2 update PASS with preservation. Smoke3 PASS at20:53UTC. Later outage reported21:18:53UTC, confirmed21:27:13UTC after Codex restart; exact termination event unavailable. Controller restores same207c source/data separately without seed/migrate/build.", "evidence_keys": ["runtime_acceptance", "runtime_review", "runtime_outcome", "runtime_first_failure", "availability_outage"], "availability_as_of_utc": "2026-09-21T21:27:13.1597409Z", "availability_basis": "False denotes only the saved outage observation at the exact timestamp. It is not a new current liveness probe. Controller owns restoration; latest serving state, new process identities and HTTPS URL are in the external final delivery.", "recovery_owner": "controller 01a0bf0f-a9e4-7631-87e1-bb1aed03f174", "last_successful_smoke_at_utc": "2026-09-21T20:53:00.262288+00:00"}} [runtime_acceptance](evidence/closeout-v17/runtime_acceptance.json), [runtime_review](evidence/closeout-v17/runtime_review.json), [runtime_outcome](evidence/closeout-v17/runtime_outcome.json), [runtime_first_failure](evidence/closeout-v17/runtime_first_failure.json), [availability_outage](evidence/closeout-v17/availability_outage.json) |
| Current review browser smoke | PASS_SCOPED_4_OF_4_HISTORICAL_AT_2053UTC | {"details": {"status": "PASS_SCOPED_4_OF_4_HISTORICAL_AT_2053UTC", "attempt": 3, "PASS": 4, "FAIL": 0, "NOT_RUN": 0, "routes": ["workpoints", "orders", "procurement", "network"], "scope": "Four read routes at1440x1000 and20:53UTC, normal owner login, source207c and app hash. Orders acceptance is visible sales heading plus authenticated snapshot; not all per-order next actions. No business POST. This does not establish availability after the later outage.", "history": "Actual1 FAIL0/0/4: missing post-login wait. Actual2 FAIL0/1/3: route assertion before loading completed. Both preserved; v3 unexecuted locator HOLD corrected in v3a.", "console": "One expected startup401 for unauthenticated /api/auth/me/. No page errors, request failures or blocked business requests; no blanket clean-console claim.", "cleanup": "At20:53UTC owned browser/profile cleanup completed and server handles were running. Later outage supersedes present-liveness assumptions.", "foreign_actual_review": "Independent historical smoke acceptance is in smoke_actual_review. Its docs HOLD concerns the superseded33-file availability wording; successor acceptance is recorded by exact root integration approval.", "evidence_keys": ["browser_receipt", "browser_outer", "browser_host", "browser_preparation_review", "browser_first_failure", "browser_second_failure", "smoke_actual_review"]}} [browser_receipt](evidence/closeout-v17/browser_receipt.json), [browser_outer](evidence/closeout-v17/browser_outer.json), [browser_host](evidence/closeout-v17/browser_host.json), [browser_preparation_review](evidence/closeout-v17/browser_preparation_review.json), [browser_first_failure](evidence/closeout-v17/browser_first_failure.json), [browser_second_failure](evidence/closeout-v17/browser_second_failure.json), [smoke_actual_review](evidence/closeout-v17/smoke_actual_review.json) |
| Final-head remote CI | PENDING_POST_PUSH_OBSERVATION | {"details": {"status": "PENDING_POST_PUSH_OBSERVATION", "as_of": "Private docs preparation before its ordinary commit/push. Exact final-head runs/jobs are recorded in external final delivery and PR.", "forced_full_suites": false, "skipped_is_pass": false, "automatic_reruns": false}}  |

Ранее зелёные CI workflows с пропущенными jobs не считаются PASS этих jobs. Full P05/PG/E2E, production activation/upgrade/rollback и старые заблокированные browser-маршруты не перезапускались этим отчётом.

## Открытые проблемы

### V17-01 · P2 · Private employee membership preview

Статус: OPEN_PRIVATE_NOT_PUBLISHED. Blocks private union acceptance; duplicate committed Employee mutation not established.

Воспроизведение/проверка границы:

1. Open private combined MembershipDialog.
2. Create preview successfully.
3. Invoke retained prior form-submit handler with unchanged intent/facts.
4. Observe second mocked preview proposal (2 instead of 1).

Private v5 adds current-owner proposal guard. Static accepted, behavior NOT_RUN, shared apply0.

### V17-02 · P1 · Full linked business/role/restart acceptance

Статус: OPEN_ACCEPTANCE_GAP. No complete evidence for this path on published source; not an observed data-loss claim.

Воспроизведение/проверка границы:

1. Follow S1/S2/S3 end to end through current UI as distinct non-CEO roles.
2. Verify persisted amounts/source refs and Task actual result after separate server reopen.

Use frozen protocol only after future owner instruction; no automatic execution.

### V17-03 · P2 · P06-F04/F05 timeout causes

Статус: OPEN_DIAGNOSTIC. Root cause unresolved; no runtime fix proven.

Воспроизведение/проверка границы:

1. Refer to original P06 failed runs and PLAN_TIME_RESULTS_UA.md.

Bounded future diagnosis subject to P05 history; do not launch full retry to reproduce.

### V17-04 · P2 · Department work queue and Task completion

Статус: PARTIAL_IMPLEMENTATION. New queue and membership union remain private; full department work cycle is not accepted.

Воспроизведение/проверка границы:

1. Follow existing same-Task handoff in synthetic chain.
2. Inspect actual_task_result: empty; process/done was not demonstrated.

Apply only future accepted union and prove actual result/rights/current UI.

### V17-05 · P3 · Historical build/process evidence

Статус: KNOWN_EVIDENCE_LIMIT. Successful build exits and archive bytes are accepted; exact capture protocol completeness is false.

Воспроизведение/проверка границы:

1. Inspect accepted SDC source package build capture records.

Keep disclosed original gaps; no retroactive receipt fabrication or repeat just for a cleaner report.

### V17-06 · P1 · Availability after Codex restart

Статус: RECOVERY_DELEGATED_AT_SNAPSHOT. Historical four-route PASS does not prove present availability. Parent-lifetime coupling is inferred, exact termination event unavailable.

Воспроизведение/проверка границы:

1. Original temporary URL returned Error1033 after Codex restart.
2. Saved outage observation21:27UTC has no old serving PIDs or listeners.

Controller restores same app/data through serving processes independent of Codex; final external delivery records checked URL and outcome. Do not rebuild, seed or replay UI suites.

## Порядок ручной проверки

1. Открыть http://127.0.0.1:8876/ на компьютере стенда, получить локальный логин через точную PowerShell-команду выше и войти обычной формой.
2. Открыть рабочие точки и выбрать филиал; проверить сохранение контекста, единицы и UAH.
3. Перейти в заказы, закупки и сеть/отделы через существующее меню; проверить доступность списков, понятные пустые состояния и источники выбранной записи.
4. Проверить compact navigation и подписи ручных/неизмеренных KPI. Нулевой/отсутствующий показатель не должен выдавать выдуманный рейтинг.
5. Для действий просматривать последствия preview перед confirm. Использовать только синтетические данные стенда. Сохраняемые владельцем изменения не стираются автоматически.
6. Замечания передать с маршрутом, ролью, филиалом, ID записи, ожидаемым и фактическим результатом. Проверка владельца не превращает невыполненный gate в PASS автоматически.

## Решения владельца после проверки

Сейчас требуется ручная проверка и её замечания. Затем — выбор следующего согласованного объёма: private membership/queue и общая UX/role/restart проверка, либо иной приоритет. Перед GPT/пилотом отдельно нужны допустимые данные, API-бюджет/модель и выбранный пилотный бизнес. Для публикации этой локальной review-копии повторное разрешение не требуется.

## Остановка изменений

После итоговой передачи — FREEZE_FOR_OWNER_REVIEW. Главный останавливает назначенные агентские циклы; контролёр приостанавливает существующую automation. Сервер и синтетическая БД остаются доступны. Новые этапы, тестовые повторы и изменения версии начинаются только после нового указания владельца. Фактическое подтверждение остановки, final commit/push/CI и runtime process receipt прилагаются к внешнему финальному delivery.

## Источники и переносимость

Выбранные исходные receipts скопированы без изменений в evidence/closeout-v17; MATRIX.json содержит SHA-256, размер и исходный локальный путь. Вложенные ссылки оригинальных receipts могут указывать на полные локальные raw logs. Полный принятый продуктовый архив207c сохраняется отдельным release-пакетом; новый product build этим documentation change не создаётся.
