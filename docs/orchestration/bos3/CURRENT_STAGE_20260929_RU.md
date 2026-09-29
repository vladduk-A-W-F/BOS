# BoS 3.0: текущий этап 29.09.2026

Поручение владельца: «продолжай разработку согласно плану и обнови на каком мы сейчас этапе и как идет», native message `01a0eec9-aa90-75e0-9003-f7def11ca5e5`, проверено root. Это текущая сверка стадии, не новая полная приёмка. Историческая `FULL_READINESS_MATRIX_E710.json` сохранена без изменений; её требования не отменены.

## Версия и срок

- Этап: подготовка предрелизной owner-local версии. Срок: **04.10.2026 23:59 Europe/Berlin**. Риск полного GO высокий: нет текущей доказанной доступности runtime, конечной проверки обучения и всех 11 gates.
- Product dev9: `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf`; immutable candidate: `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`; паспорт `ATOMIC_DEV9_CANDIDATE.json`, SHA-256 `1d39d2b329c5a5cfc6706caecaa99e674e40eb14c795cc82d8547851b5a37d00`.
- Документальный baseline этой сверки: `9638dce228070cef6384eebe96e3f86be237faf0`, ветка `codex/bos3-prerelease-20260927`, draft [PR10](https://github.com/vladduk-A-W-F/BOS/pull/10), без merge. Он не является новым product/runtime SHA.
- Dev9 не доставлен. Последняя принятая квитанция dev7 историческая; после failed dev8 start актуальная доступность **UNCONFIRMED**. Проверенную актуальную ссылку на dev9 выдать нельзя. Приложение этим заданием не останавливалось и не перезапускалось; БД/media/пароли/прогресс не затрагивались.
- `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`. Успешный служебный CI не является app QA.

## Состав и результат

| Пункт | Состояние полного требования | Доказанный объём и остаток |
|---|---|---|
| Актуальный owner-local кандидат | Заблокировано | Dev9 source/package приняты scoped; recovery preflight и diagnostic остановлены до выполнения. Нужен уже запрошенный точный owner scope, затем независимый admission. |
| Светлое адаптивное превью | Частично | Исходники, scoped build/offline и историческая entry-проверка приняты. Полная актуальная live desktop/mobile приёмка dev9 отсутствует. |
| Три синтетических учебных кейса | Частично | Preview и маршруты есть. B30-12 revision9 готов только к точному исключению владельца; сквозной запуск трёх кейсов NOT_RUN. Это не S1/S2/S3 полная бизнес-приёмка. |
| Персональный вход и прогресс | Частично | Историческая scoped entry/login проверка есть; актуальное сохранение завершённых шагов и повторный вход не приняты. Нужен B30-12 owner decision, не повторный вопрос. |
| Полный перенос на D | Частично | Каноническая интеграция уже на D. Исходник установщика готов и независимо принят статически, опубликован9638dce. TESTED/INSTALLED/MIGRATED=false; единственный control home пока C. |
| Exact-version доставка | Заблокировано | Immutable passport подготовлен, текущего runtime receipt на dev9 нет. Исторический dev7 receipt не переносится. |
| S1: заказ → резерв/отгрузка → счёт/оплата | Частично | Source mapping сохранён; полный текущий dynamic verdict отсутствует. Узкий invoice/UAH projection отдельно исправлен и принят, это не весь S1. |
| S2: документ → черновик → сверка → подтверждаемая операция | Частично | Source mapping сохранён; полный текущий dynamic verdict отсутствует. |
| S3: дефицит → закупка/перемещение → приёмка/качество → остаток | Частично | Source mapping сохранён; полный текущий dynamic verdict отсутствует. |
| UXD01: происхождение показателей | Частично | Scoped provenance/disclosure интегрирован8eb832a; поздний dev6 package/review сохранён. Не полная текущая live приёмка. |
| UXD02: показатель → список → запись → возврат | Частично | Три метрики с общим count/list predicate, guarded inspection и возвратом интегрированыec968705, dev7 package принят. Остальные метрики и полная cross-role приёмка не заявлены. |
| UXD03: очередь отдела и связанная работа | Частично | Реальная Task-очередь и компактная карточка интегрированыa5adcef. Раскрытие ожидания/причины отдельно ожидает уже заданного UXD03-WAIT-01 решения. |
| UXD04: передача получателю и сохранённая история | Частично | Текущий source-only trace отдельно устанавливает реальные команды, права, audit и UI. Runtime/cross-role доказательство не заменяется демонстрационными передачами. |
| UXD05: навигация и действующие кнопки | Частично | Scoped UI изменения есть; полный role-specific walkthrough не принят. |
| UXD06: читаемость, keyboard/focus, размеры/200% | Частично | Исторические offline390/1440 и CSS/focus не закрывают768/200% и live keyboard/return focus. |
| UXD07: loading/empty/error/denied/stale | Частично | Исходники изменены ранее; актуальная полная динамическая проверка состояний и повторов отсутствует. |
| UXD08: данные/UAH/права/preview-confirm | Частично | Узкая invoice-правка и её scoped QA приняты; полная сверка прав/фактов/всех поверхностей не доказана. |

Источники поздних scoped результатов: `CONTROL_STATE.json.cards`; `evidence/task-card-applicability-20260927/READINESS_DELTA_A5ADCEF.json`; `evidence/uxd01-provenance-20260927/READINESS_DELTA_8EB832A.json`; `evidence/uxd02-scope-20260927/CODE_REVIEW_RU.md`; `evidence/uxd02-monitor-qa-20260927/QA_REVIEW_RU.md`; `evidence/invoice-integration-20260928/INVOICE_INTEGRATION_REVIEW_RU.md`; `evidence/atomic-pack-20260928/CANDIDATE_REVIEW_RU.md`. Нового модельного review неизменённых принятых bytes и повторного QA здесь нет.

## Одиннадцать Gates

Требования сохранены по исторической матрице. Ни один полный gate не объявляется закрытым по текущему dev9. `NOT_PROVEN` означает отсутствие достаточного текущего доказательства, а не отсутствие реализации. Все динамические проверки в этой сверке **NOT_RUN**.

| Gate | Неизменное требование | Состояние полной приёмки / причина |
|---|---|---|
| 1 | Міграції на порожніх SQLite і PostgreSQL | Заблокировано: NOT_PROVEN; нет актуального точного допуска/evidence. |
| 2 | 151 функціональна + 5 launcher + решта тестів на обох СУБД | Заблокировано: NOT_PROVEN; full/PG suite caps сохранены. |
| 3 | П’ять інваріантів, мінімум 1000 випадкових прогонів кожний | Заблокировано: NOT_PROVEN; полного текущего допуска/evidence нет. |
| 4 | Права всіх ролей на всіх API/admin та всіх поверхнях даних | Заблокировано: NOT_PROVEN; scoped source-review не полная проверка прав. |
| 5 | Два одночасні виклики кожної грошової та складської дії | Заблокировано: P05/network3/3, нового допуска нет. ERP mutex не отменён. |
| 6 | Наскрізний процес на чистій базі, звірка до копійки | Заблокировано: NOT_PROVEN; B30-12 не подменяет полный gate. |
| 7 | Backup/restore у чисту установку: кількості, суми, версії, SHA | Заблокировано: NOT_PROVEN; source установщика не restore evidence. |
| 8 | Чиста виробнича установка: TLS, cookies, proxy, health, logs | Не начато в этом owner-local цикле: production/external scope не разрешён. |
| 9 | Оновлення N → N+1 та відновлення N після rollback | Заблокировано: NOT_PROVEN, A10 остаётся. |
| 10 | Браузер: 390/768/1440, 200%, клавіатура, Escape, мережа | Заблокировано: полной dev9 проверки нет; A11 не обходить. |
| 11 | Чиста Windows / Python 3.12: критерії 1–3 і 6 | Заблокировано: NOT_PROVEN; Windows diagnostic не даёт приёмку. |

## B30-12 И Следующая Работа

Механически сверены **13/13** Git blobs из revision9 manifest с immutable dev9: совпадают. Сравнение dev7→dev9 в frontend/assets/tasks/training/erp/operations показывает только изменения `erp/experience.py` и `erp/test_home_projection.py`; поэтому прежние UI/Task/training bytes не требуют повторного code-review только из-за нового документального HEAD. Это не полная проверка зависимостей harness и не перенос e710 admission: template всё ещё содержит `PENDING_OWNER_EXCEPTION_ID`, e710 и старый путь source. После действительного ответа владельца нужен final manifest на точный выбранный pin и независимый admission review. Исходный template и review не переписаны. Подробности: `evidence/uxd04-trace-20260929/B30_12_DEV9_BYTE_COMPARISON.json`.

Полезная разрешённая часть завершена и независимо принята: **B30-UXD04-SOURCE-TRACE-20260929**, отдельный scratch, 17 закреплённых файлов. Найдена реальная цепочка handoff_task → preview/confirm → Task/AuditEvent/receipt → список и история получателя; конкретный source дефект не установлен. Вердикт `ACCEPT_SCOPED_SOURCE_EVIDENCE_AND_CURRENT_RECORDS`, review SHA-256 `ec0d3adc6fe3f56c7f7e062e6599ab1e7ffd394b2d751348d8be53d9e8f5151a`; root публикует только документационный результат, фактический commit/PR/receipt отдельно фиксируются во внешнем `D:/3/BOSDev/evidence/plan-continuation-20260929/ROOT_PUBLICATION_RECEIPT.json`. `TRACE_RU.md`, `SOURCE_MANIFEST.json`, `NEXT_SCOPE.json` и `INDEPENDENT_REVIEW_RU.md` в `evidence/uxd04-trace-20260929/` задают точные source refs и границу недостающего cross-role доказательства. Разбор не добавляет domain semantics и не открывает QA. Initial manifest пропуск operations/views.py и найденная reviewer неточность P2 о четырёх sessionStorage identifiers исправлены исходным автором; первые snapshots сохранены в author-initial. Это исправления документации, не дефекты приложения; raw/source тестов и runtime исполнения здесь нет.

История ограничений не сбрасывается: P05/full/PG/E2E3/3; fixture3/3; progress Node exception1/1; focused control-home QA1/1 **FAIL_SETUP**, bodies0, remaining21 **NOT_RUN**; runtime problem2/3; preflight1/1; observation1/1; старый start1/1; inventory3/3; parser1/1; C64 policy refusal1/1; A09/A10/A11. Дополнительные fixture-diagnostic, C64, B30-12 и UXD03 вопросы уже переданы владельцу; здесь не повторяются. Runtime, повторные tests/probes, миграция и доступ без нового точного допуска не выполняются.

До30.09 зафиксирован риск срока. 01.10 требуется реалистичный состав версии в рамках сохранённых требований; 02–03.10 только разрешённые финальные проверки; 04.10 лучший подтверждённый результат либо явный NO-GO. Календарь не снижает критерии. Heartbeat тот же15min; observer native goal usageLimited отдельно от него, не completed. Новый чат/таймер/цель не создавались.
