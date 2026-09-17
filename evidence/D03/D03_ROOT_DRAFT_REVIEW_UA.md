# D03 · незалежний review чернетки root

12.09.2026. Перевірено лише зміст і diff кандидатів `tmp/d03_root_docs` (7 документів) та `tmp/d03_ui_copy` проти незмінної canonical C03. Тести, браузер, API, сервер та БД не запускалися і не читалися. Жоден файл canonical або кандидата не змінено. Full26 ще не використаний як підтверджений результат.

**Висновок:** у перевірених змінах документів та одного UI-абзацу нових блокерів поведінки або прав не знайдено. F01/F02/F05 закриті, F07 закритий у наданому scope. F06/F08 частково очікують заплановані TEST_REPORT/ERP_GUIDE; F03/F04 і повне D03 приймання цим review не закриваються. Перед остаточним пакуванням потрібні актуальний manifest та наявні цільові файли посилань.

## Звірка зауважень

| Зауваження | Результат чернетки | Точне місце |
|---|---|---|
| F01: назва меню виписок | Закрито. Для CEO використано фактичне «Фінанси → Операції → Виписки». Internal route `bank` не змінено. | `tmp/d03_root_docs/README_UA.md:78`, `docs/STATEMENTS_UA.md:9`; canonical JSX:289 |
| F02: DB-only restore | Закрито. Launcher backup прямо названо копією лише SQLite. Окремо вказані `rehearsal-media`, узгоджений комплект після зупинки й відсутність прийнятого automatic local-demo restore. Серверна A10-інструкція не видається за універсальний restore. Повтор демо — нова папка. | `tmp/d03_root_docs/docs/DEMO_AND_IMPORT_UA.md:22,28–32` |
| F05: 20 000/21 600 та cash | Закрито. Чітко зазначено 20 000 початкових I01–I03 + 1 600 додаткових ERP-прикладів; висновок позначено як розрахунок із синтетичних seeds. 24 000 відділено від C03 cash/журналу; свіжий набір і роль задані. | `tmp/d03_root_docs/docs/DEMO_AND_IMPORT_UA.md:5,13` |
| F06: строк/FK/результат доручення нібито не реалізовані | NEXT_STEPS виправлено: перелічено вже реалізовані відповідального, строк і результат. Старий TEST_REPORT:25 не змінено у цьому пакеті — очікувана окрема правка після full26, тому глобальне закриття передчасне. | `tmp/d03_root_docs/docs/NEXT_STEPS_UA.md:18–20`; canonical `docs/TEST_REPORT_UA.md:25` |
| F07: акаунти нібито не підключені | Закрито для README/MVP/NEXT_STEPS та видимого BoSProductGuide. Демо-акаунти, справжній робочий вхід і непройдене загальне серверне приймання розмежовано. CSV не видається за банківські перекази. | `tmp/d03_root_docs/README_UA.md:46`; `docs/MVP_GUIDE_UA.md:62`; `docs/NEXT_STEPS_UA.md:20`; `tmp/d03_ui_copy/frontend/boss_app_source.html:4198` |
| F08: повний показ без передумови ролі | README/MVP/DEMO задають Керівника і свіжі дані; MVP/DEMO також дозволи документів/завантаження. Рольовий доступ не розширено. ERP_GUIDE передумова ще очікує окрему правку, а фінальний ROLE_GUIDE перевіряється окремо. | `tmp/d03_root_docs/README_UA.md:26`; `docs/MVP_GUIDE_UA.md:16`; `docs/DEMO_AND_IMPORT_UA.md:5`; canonical `docs/ERP_GUIDE_UA.md:40–53` |

Додаткові вузькі виправлення правильні: backup-таблиці 45 позначені історичним A10 checkpoint, 56 — очікуваним C03 набором конкретної версії; старі 10/10 відділені від актуального результату. ACCESS уточнює локальний A08 та CEO-only CSV. NEXT_STEPS зберігає B04–B07 за рішенням клієнта, зовнішню модель/черги/локальну LLM поза поточним scope і не обіцяє релізну дату.

## Залишки перед freeze

1. **Одна мала термінологічна неточність:** `tmp/d03_root_docs/docs/NEXT_STEPS_UA.md:20`, «backup у нову керовану установку». Рекомендовано «резервне копіювання та відновлення в нову керовану установку». Backup створює копію; restore створює нову установку. Це не новий поведінковий дефект.
2. Manifest документів відстає лише для NEXT_STEPS, як root попередив. Base SHA усіх 7 файлів правильні; 6 candidate SHA збігаються. Перевірений NEXT_STEPS після виправлення «вигрузки» має SHA `057433e5440d7ebb5f90a5e00c34e1bb7e7cbe6a484d8ef95047ac78418b728e`, а manifest ще `55ceb575…`. Остаточний manifest треба перезаписати після завершення редактури, не інтегрувати цей mismatch як freeze.
3. Нові посилання на ROLE_GUIDE й CSV мають відповідні файли у `tmp/d03_docs/`; їх слід включити в canonical `docs/` разом із пакетом. `docs/STATEMENTS_UA.md:5` посилається на ще відсутній `evidence/C03/RESULT_UA.md`; його root готує після full26. У перевіреному overlay решта явних локальних Markdown-посилань мають наявні цілі. Наявність чернетки не означає фінальне приймання її змісту.
4. README:60 уже називає TEST_REPORT навігацією актуальними доказами, але це стане правдою лише разом із запланованим новим TEST_REPORT. ERP_GUIDE/TEST_REPORT та F04 operator bootstrap не входять у перевірені 7 документів і не оголошуються готовими. F04 автор a09 має описати чесну межу підтриманого bootstrap, без вигаданого CLI.

## Незмінність інтерфейсу

Manifest UI: `90cd906baac2b77758ddabbc82e5816736eaf31eac7b4bb02cff377dc49c45b3`.

- Чинний source C03 `78136013…` містить старий абзац рівно один раз. Заміна його **точно на** `source_exact_replacement.after` дає побайтово весь кандидат `217ef22b26ef0b551bf6be8588f350eee5928d7a2bf6146571d655e48e35c4e3`. Інших змін JSX немає.
- `frontend/boss_app_html.html` побайтово незмінний: `e215f02aa69d5931cbc41dca742fd850a02c471d07d45fc66a75c9aa3e244937`.
- Порівняння **всього** app.js показало одну змінену лінію 16055. Декодовані JSON text literals точно збігаються з before/after manifest; prefix/suffix рядка та всі інші рядки побайтово незмінні. Кандидат: `0285afed1b3a34eefc9bfdd406fda7a8a058ae5317707195fea5d938af7c29bd`.
- `scripts/build_frontend.cjs` та `assets/babel.js` рівні canonical. SHA обох наданих BUILD/SYNTAX logs збігаються з manifest. BUILD.log містить `JSX compiled; local script assets wired.`, SYNTAX.log порожній. Root повідомив успішне фактичне виконання; цей reviewer компілятор/Node повторно не запускав.

Отже actions, role guards, data sources, B02/B03/C01/C03 форми та модальні переходи не змінені навіть побайтово за винятком цього одного літерального тексту. Це source/compiled-scope висновок, **не браузерне приймання**.

## SHA документів цього прочитаного checkpoint

| Шлях у tmp/d03_root_docs | Фактичний SHA-256 |
|---|---|
| `README_UA.md` | `0d584dd9944fa05a2e40b0c062a640bf8e62d8ef4ed1a7d3e49563dcb16aaf56` |
| `docs/STATEMENTS_UA.md` | `59f57cd574423b5bfe3617945b3a2754aba48567c7728431f348992626db7b06` |
| `docs/MVP_GUIDE_UA.md` | `f38a28f4bf7a9765fc34f69fd042c4320ce5195704b0bba2256f909bdb350368` |
| `docs/DEMO_AND_IMPORT_UA.md` | `35c51fb16301c57162abf06b9262fef9524a63fa070768bae7e7f25ee6e584c6` |
| `docs/BACKUP_RESTORE_UA.md` | `ec7235d0a915c04fc5cdfbaf4fd97c5da296696d5dadedfeb6c000620fa7df87` |
| `docs/ACCESS_UA.md` | `82d09953fd467a6c5f81183a012354ecf11cb5195a3b32fbf892b201da85f39a` |
| `docs/NEXT_STEPS_UA.md` | `8f9b7f7efcfa28dc43b9f4e2a954661fa8e2dd6309575cf2f873ade5002c39fa` |

Перевірений draft manifest: `a4a9ac410930d42d0e8c7edf128541a2c53a7c90f11a0b23ad0b82c4d3f6e791`. Перший аудит: `tmp/D03_DOCUMENTATION_FACT_AUDIT_UA.md`.
