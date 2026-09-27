# B30-PREVIEW-LIGHT: проверка кандидата

Дата: 27.09.2026. База реализации: defd1fc12545053159a3a888013d096c79157fd3. Отдельная копия: C:/Users/user/.codex/worktrees/bos3-entry-flow/repo. Root единственный интегратор.

## Границы и происхождение

Прямые уточнения владельца: светлое интерактивное превью вместо тёмной брошюры; единый дизайн телефона и компьютера; зелёный акцент, узнаваемые значки, диаграммы и понятный контекст; начало обучения из выбранного кейса. PDF вспомогательный. Исходный ориентир: отдельный Sites v3, ce0322034971a1ddc5cd66470e3792bb26f56493, public/index.html, landing.css, landing.js. Старый Sites checkout и данные «Опоры» не менялись и не переносились.

Автор UI: start_overview_implementation. Allowlist: frontend/boss_app_source.html и display metadata presentation.chart в frontend/bos3_content.json. Backend, auth service, уроки, fixture и CRM не изменялись.

Финальный source SHA-256: 5F23F53B0A3FBF4C467844E493A8ABDDB6A65EC48BA01C37BEDCD1555BA9B4B0.
Финальный registry SHA-256: 1BCE859370537437C157893065AF499C9EDD0FEFEA90B30C2F3384B2B04B1390.

## Независимое ревью

- Предыдущая source-ревизия CFC3674... была принята start_overview_review только статически. Последующее прямое уточнение о диаграммах стало причиной нового delta review; прежний verdict не автоматически перенесён.
- «БОС — отдел дизайна», 01a0bffa-3fc7-7bc2-9868-86164c6e0315: ACCEPT_STATIC по переданному root финальному git diff и двум hash выше. Доступ к source через собственный shell отдела был UNCONFIRMED; результат честно ограничен snapshot, не browser acceptance.
- Поправки дизайна: явно восстановлены 11 областей, локализован aria-label, input имеет 16px. Предложение дополнить экран объяснением URL-механики отклонено root как лишний инструктивный текст, не дефект поведения.
- Арифметика и контекст: 140 готовых + 360 запланированных = 500 комплектов; 120 шайб показаны отдельно. 250 допущенных + 20 заблокированных = 270 проверенных остатков, не отгрузка. 10 000 оплачено + 6 400 открыто = 16 400 грн. Это исходные учебные факты, не динамический прогресс.
- start_overview_review: ACCEPT_SCOPED_STATIC финального кода на двух hash выше, без P1/P2. Отдельно ACCEPT_SCOPED_AST_ORACLE файла check_b30_preview_entry.cjs, SHA-256 BA338AEFBC2B5796EBCF0351E5FD52A8A6860E190AA3FF98529A0240EEDE33BF. Независимый reviewer не запускал проверку.

## Адресная QA

Классификация: SAME-PROBLEM entry-flow, следующая попытка 2/3. Попытка 1/3 на dev.2 сохраняется как историческое scoped доказательство, не финальная проверка нового UI. Progress exception 1/1, fixture 3/3 и другие лимиты не изменяются.

Старый oracle сохраняется неизменным в evidence/entry-20260927/. Legacy QA подготовил новую версию для намеренно изменившейся структуры UI. До запуска root нашёл и исправил через автора два ложных ожидания: AST не раскрывает React-компоненты, а public form называется entryPasswordForm. Последующий доступ QA-чата к final schema был UNCONFIRMED; запуск не выполнялся. Root добавил один chart assertion по фактическому diff и передал весь oracle независимому reviewer. Переназначение исполнителя не обнуляет попытки.

Никаких browser, HTTP, server, DB, fixture, init, seed, migration или lifecycle действий этим review не выполнялось. Desktop/mobile пока проверены только по CSS source. Защищённая рабочая область сохраняет прежнюю тему; светлый дизайн этого кандидата относится к preview и входу.

Фактическое исполнение root: entry attempt 2/3, 9/9 PASS, native exit 0. Source и registry hashes в raw результате совпали с reviewed pin. Одна штатная сборка новой ревизии: native exit 0, `JSX compiled; local script assets wired.` Доказательства: entry-attempt-2.raw.txt, entry-attempt-2.receipt.json, frontend-build.raw.txt и frontend-build.receipt.json. Повторных запусков не было.

При интеграции apply_patch нормализовал окончания строк source. Root сравнил обе версии после нормализации CRLF и подтвердил, что семантических различий нет, затем восстановил байт-в-байт reviewed source из worker copy. Итоговый SHA снова 5F23F53B...; QA и сборка выполнены именно на этих байтах.

## Доставка и готовность

Runtime остаётся dev.1 / 33d7d387aa582c04339a91ae94361948ea67904c. Ответ владельца на уточнённый вопрос продолжил требования к стилю и отделам, но не дал точного lifecycle/browser-исключения. Новый код не выдаётся за установленный сервер. TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false.
