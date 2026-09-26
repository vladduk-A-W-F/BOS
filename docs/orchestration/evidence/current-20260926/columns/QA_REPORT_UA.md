# UI-COLUMN-CONTENT-01 · незалежний QA

## Межа

Перевірено лише ізольовану копію
`C:\Users\user\.codex\worktrees\bos-column-content\repo` від
`a3c0596ab611290ba5ad199f55309812093f908b`.

Картка охоплює текст комірок та фактів `CoreModuleSurface` /
`ModuleRecordFacts`, дескриптори колонок та їхні CEO/manager/observer fixtures.
Не запускалися Django, БД, PostgreSQL, мережа, CI, E2E, legacy browser suite або
реальний застосунок.

## Результати

| Команда | Exit | Результат |
| --- | ---: | --- |
| `node scripts/checks/module_column_content.cjs` · спроба 1 | 1 | Збережена невдала перевірка harness: `0 == 4`. |
| `node scripts/checks/module_column_content.cjs` · спроба 2 | 1 | Збережена невдала перевірка harness: `0 == 4`. |
| `node scripts/checks/module_column_content.cjs` · спроба 3 | 0 | PASS: 4 адресні перевірки fallback, нулів, семантичних однойменних фактів, `label_field` і role fixtures. |
| `node scripts/checks/module_views.cjs` | 0 | PASS: 25 наявних компонентних/контрактних перевірок доступів, дій, подань і форматування. |
| `node scripts/check_frontend.cjs` | 1 | `FAIL_LEGACY_LEXICAL_CHECK`: `getComputedStyle` не внесений до allowlist. Reviewer підтвердив, що виклик на frontend line 754 та checker blob незмінені цією карткою. Це не PASS і не змінювалося. |
| `node scripts/build_frontend.cjs` | 0 | PASS: JSX compiled; local script assets wired. |
| `git diff --check` | 0 | PASS. |

Повний stdout/stderr content і точні команди лежать у `*.command.txt` та
`*.stdout-stderr.txt` поруч із цим файлом; їхні line endings нормалізовано до
LF лише для перевірюваного Git evidence. Повна історія трьох focused-спроб:
`QA_HISTORY.md`; ліміт не перевищено.

## Артефакти та SHA-256

| Артефакт | SHA-256 |
| --- | --- |
| `frontend/boss_app_source.html` | `3D2F1092C0B4E99347816CF7AADC1F7062E9DB8B2C1F5FA80FB12D0A08538FE3` |
| `erp/module_registry.py` | `9BC776087E2DBA547FA521A61624B0E50C096CE8DB32B5650515AFCB02E304ED` |
| `scripts/checks/module_column_content.cjs` | `8BDEA68BDA813522D7F0EE1C6CFD114AB8EB0DD5BBD14BF3FBA5023F97602682` |
| Generated `frontend/boss_app_html.html` | `D7202D2164918A60507A9A67456A30FEFC553EC9B77A2A0E2AE6E9A7F681CCE5` |
| Generated `assets/app.js` | `05FF8E1AE206708F9AA918D29F201D793F5BF44A0A34B10196766F6D8A1F80A4` |
| Static fixture `columns_static_fixture.html` | `DF3A5648B404C9C6F0F9E731466095D275F7C1135C55ED3DE3236CB5EA71846B` |

## Візуальна перевірка

Підготовлено ізольовану React/Babel fixture
`columns_static_fixture.html`: синтетично показує тільки змінені flow-картки та
деталі фактів, включно з перенесенням, відсутніми значеннями, нульовими
кількістю/сумою, однойменними семантичними фактами та відсутністю дії для
спостерігача.

Bundled Node не містить `playwright`, `playwright-core` або `@playwright/test`.
Спроба відкрити fixture через in-app browser з `file://` була відхилена політикою
дозволених протоколів (`http:`/`https:` лише). A11 і явна заборона інструмента
не дозволяють обхід через loopback, data URL, CDP або інший браузерний маршрут.
Тому desktop 1440/mobile 390 screenshots **не створені**, а browser visual QA
не заявляється виконаним.

## Висновок

`ACCEPT_SCOPED_WITH_GAPS`: адресні display-контракти та build пройшли; одна
незмінена legacy lexical-перевірка має exit 1, а статичний browser-render
заблоковано політикою середовища. Це не змінює жоден із 11 GATES,
`TECHNICAL_READY`, `PILOT_ALLOWED` або продуктову готовність.
