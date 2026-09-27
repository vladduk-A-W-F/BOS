# Контроль всего проекта BoS

27.09.2026. B30-PROJECT-CONTROL. Прямое поручение владельца «ПО ВСЕМУ ПРОЕКТУ», принято через действующий координационный контур. Root сохраняет единственную canonical копию и последовательную интеграцию. Это расширение охвата контроля, не разрешение произвольных новых функций или повторных тестов.

## Принятый протокол

Действует точный reviewed CONTROL_PROTOCOL_RU.md из evidence/projectwide-control-20260927/. SHA-256 73935537E56D5E104EDF8EE0BF425F3EBAF135C4B3CF35BBA03C66C97A9B76A1. Независимый внешний REVIEW_AFTER_UPDATE_RU.md: ACCEPT_SCOPED; прежний CHANGES_REQUESTED сохранён. IMPORTED_SNAPSHOT.json фиксирует байты полученных источников. Их промежуточные статусы являются датированными snapshots, а не текущими распоряжениями.

На момент принятия root: B30-PREVIEW-DELIVERY уже завершён и записан commit 1015179f54a5b60ece18a3d69a81bdef9229cb52. Runtime/product f55a15de4006d10c0d7c65f8a2ca8499fbb99819, dev.3; scoped delivery/entry принят независимо. Старые pending permission, runner not executed и незакрытый stale next_action в импортированных отчётах заменены этим результатом. Полная готовность продукта не заявлена.

Контролируются backend/ERP/CRM, контракты данных, frontend/UX, auth/права, обучение/прогресс, QA/fixtures, документы/PDF, упаковка, доставка, инструменты и межотдельские передачи. На каждое направление работа назначается только при конкретной разрешённой карточке. Отсутствие задачи не заполняется повторным аудитом принятого кода.

## Текущие передачи

| Получатель / роль | Принятый факт | Следующее действие |
| --- | --- | --- |
| Root, 01a0dd56-ca2d-79c0-b159-bde80074a026 | Canonical bos-consolidation-plan/repo; delivery1015179, runtime/product f55 | По одному интегрировать reviewed результаты; обновлять PR и затронутые роли |
| «БОС — главный оркестратор», 01a0be90-e790-7351-a8ac-059d523941c4 | Передал reviewed protocol; существующая automation ACTIVE/15min | Следить за передачами всего проекта; не писать canonical или runtime |
| «Предложить параллельные процессы», 01a0bf0f-a9e4-7631-87e1-bb1aed03f174 | Независимый контролёр и владелец существующей native goal | Получать новый результат через observer ledger; не повторять ACK |
| «БОС — отдел дизайна», 01a0bffa-3fc7-7bc2-9868-86164c6e0315 | B30-DESIGN-NEXT, actual workspace bos3-product-design/repo; reported HEAD32acfb6, f55 ancestor подтверждён tracker | Вернуть неизменный patch/commit, hashes, точный allowlist и raw QA для независимого review root |
| «БОС — реализация и проверка пакетов», 01a0be9f-b413-7822-9f93-16ba69f4f00f | Metadata receipt подтверждён; прежний f55 package интегрирован | Не перепаковывать f55; новая упаковка только после следующего accepted product |
| QA, 01a0c05d-6eeb-79f1-a135-be66985b442f | Прежний UNCONFIRMED чтения current control/manifest снят | Только назначенный exact candidate и допустимый oracle; metadata access не QA PASS |
| «Выполнить план для лендинга BOS», 01a0bec4-431a-7d81-b858-a18ca96bd0af | Завершённый reference-only brief | Без отдельного нового предмета не запускать Sites или повторный дизайн |

Actual design path: C:/Users/user/.codex/worktrees/bos3-product-design/repo; branch codex/bos3-product-design; HEAD32acfb6ad3a0aeabe2f7501a28ba878dfeaeec87. Tracker подтвердил ancestry f55 с native exit0 в 14:15:49Z. WIP: frontend/boss_app_source.html, frontend/boss_app_html.html, frontend/bos_design.css, assets/app.js, docs/design/BROCHURE_MONITOR_20260927_RU.md. Это сообщённый состав, не принятый patch или разрешение расширять allowlist. До exact handoff implementation_acceptance=false; новый runtime не заявлять.

Три child роли дизайна уже назначены: learning_design, design_coverage, visual_qa. Root не создаёт второго UI автора; максимум четыре независимых исполнителя с учётом этих детей. Общий UI принадлежит одному автору; остальные только непересекающиеся артефакты или read-only review. Если новый handoff содержит пересечения или неизвестный допуск QA, root возвращает конкретный finding автору.

## Исполнение без зависания

На каждом содержательном переходе фиксировать owner, reviewer, QA, source/workspace/allowlist, зависимости, результат, evidence/review/integrated/runtime pins, check-in и следующий шаг. Доставка сообщения не равна выполнению. Готовый результат сразу передаётся reviewer; после принятия root интегрирует, обновляет PR и информирует потребителей. Просроченная передача получает один адресный запрос с новым основанием; неизменный blocker не порождает бесконечных уведомлений.

B30-DESIGN-NEXT: следующий check-in действующего heartbeat после этого commit, максимум15 минут при работающем приложении. Root ждёт exact immutable handoff, не неизвестный runtime доступ. Затем independent code/evidence review, проверка применимости лимитов NEW/SAME-PROBLEM и последовательная интеграция. Текущий accepted f55 не требует нового успешного validator/build/browser запуска из-за этого документа.

Обычные независимо проверенные owner-local обновления доводить до установки по постоянному поручению владельца. Сохранять DB/media/password/progress; запреты reset/init/seed/migrate, исчерпанных автоматических повторов, external access, production/main, архитектуры, прав/секретов сохраняются. Readiness=false. Нельзя отождествлять «весь проект под контролем» с «весь проект проверен».

Существующая automation обновлена проектным контролёром штатно; root не создаёт нового расписания. Продолжать после промежуточной поставки dev.3 до недельного cutoff или прямого отдельного freeze владельца. После 04.10.2026 23:59 Europe/Berlin только чтение, итог и штатная пауза; приложение не останавливать. Проверка настройки расписания не гарантирует непрерывную работу при выключенном ПК.

## Следующая независимая подготовка QA

Observer сообщил новый ACTIVE собственной native goal полной доказанной готовности. Root не создаёт вторую goal и не заявляет прямую проверку чужого get_goal; старый BLOCKED сохранён исторически. Цель полной готовности не обнуляет ограничения и не продлевает cutoff. Внешняя FULL_READINESS_MATRIX.json в D:/3/BOSDev/evidence/bos3-readiness-20260927/ является входом для сверки, не автоматически принятой новой реализацией или динамической QA.

После свежего wait_threads QA idle и поиска существующего пакета назначена read-only подготовка B30-12-QA-SCOPE в рамках B30-12/B30-00/B30-05. Исполнитель существующий QA 01a0c05d-6eeb-79f1-a135-be66985b442f, reviewer start_overview_review. Product f55, control base1015179; единственный output/allowlist D:/3/BOSDev/qa-scratch/bos3-readiness-scope-20260927/. Canonical/runtime/БД не изменять, новых subagents не создавать.

Результат: требование -> существующий код/историческое evidence -> оставшийся gap -> oracle; три кейса и completed-step reload/relogin/resume; NEW/SAME-PROBLEM с полным cap ledger; проект отдельной синтетической среды без её запуска; точные необходимые ERP/CRM writes, команды, максимум попыток, stop rules и raw receipts. S1/S2/S3, UXD01–08 и release gates сопоставить, не переписывать существующую реализацию по одному отсутствию final evidence. До независимого review нельзя запускать тесты, browser, setup/seed/migrate/reset или формировать видимость PASS. Если нужен exception, подготовить один конкретный вопрос владельцу после review. Следующий check-in текущим heartbeat; работа независима от дизайн WIP.
