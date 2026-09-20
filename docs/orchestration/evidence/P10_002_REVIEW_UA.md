# P10-002 · незалежний фінальний огляд

Дата: 19.09.2026. Reviewer: незалежний агент `p10_sequence_review`.

**Рішення: ACCEPT_SCOPED.** P06-F01 підтверджено виправленим для нового демонаповнення. Нових регресій у перевіреному обсязі не виявлено. Загальне приймання картки та продукту цим результатом не закривається.

| Об’єкт | Статус |
|---|---|
| P06-F01 | VERIFIED лише для fresh demo seed |
| P10-002 | BLOCKED_FULL_ACCEPTANCE: дозволена вузька робота цього ходу завершена |
| Full на новому source | NOT_RUN за чинними обмеженнями |
| P06 | BLOCKED |
| TECHNICAL_READY / PILOT_ALLOWED | false / false |
| P05 timeout cycle | 3/3, не скинуто |

## Кандидат і походження доказів

Єдиний кодовий commit: `7d46dced3bcf06d44755cf53366c9e16bd465582`, приватна гілка `fix/p10-002-task-sequence-20260919`.

Runtime/source SHA256: `10d86748d682926a898d2d2dfecd43fd7f6962f6ed38602da7ae704e52aca154`. Reviewer незалежно обчислив цей digest за чинним алгоритмом для 338 файлів; збіг із CI підтверджено. SHA усіх чотирьох файлів правки збігаються з передзапусковим оглядом PRELAUNCH_UA.md; додаткового code delta після огляду не виявлено.

Baseline: `b11aa8ce8f5855c34fa197e35b8fe77a850e9df0`, початковий source `c324a157493fb9681ba0d55bfcfdbf70e402d07cae5c48338481fb975ab2e0d8`. До окремого baseline checkout додано лише той самий regression test; початковий source перевірений runner до додавання.

Фактичний CI: [run 35470413616](https://github.com/vladduk-A-W-F/BOS/actions/runs/35470413616), attempt 1, job `105970219252` за збереженим PROVENANCE.json. RUN_FINAL.json підтверджує event=push, потрібні branch/commit, completed/success та run_number=1. JOB_LOG.txt підтверджує candidate checkout і виконання трьох вузьких фаз. Середовище: Ubuntu 24.04.5, Python 3.12.14, PostgreSQL 16.15.

## Фактичний red → green

| Фаза | Raw результат | Exit | Висновок |
|---|---|---:|---|
| PostgreSQL baseline, один test | `tasks_task_pkey`, `Key (id)=(1) already exists.`, `Ran 1 test`, `FAILED (errors=1)` | 1 | Точний очікуваний контрприклад |
| PostgreSQL candidate, шість tests | Усі шість імен мають `ok`; `Ran 6 tests in 1.701s`, `OK` | 0 | PASS у заявленому обсязі |
| SQLite candidate, ті самі шість tests | Усі шість імен мають `ok`; `Ran 6 tests in 1.090s`, `OK` | 0 | PASS переносності у тому самому обсязі |

Reviewer прочитав самі raw traces та кінцеві summary. Red виник безпосередньо на `Task.objects.create` після seed, а не на setup, timeout або сторонньому assertion. У двох green немає skipped tests або незавершеного summary. PostgreSQL до/після використовували різні свіжі `test_bos_verify_*` БД; логи містять їх створення та знищення. SQLite використовувала окрему тимчасову test DB.

## Семантика правки та регресій

Зміна додає штатний `connection.ops.sequence_reset_sql(no_style(), [Task])` після вставки явних demo ID 1..8, у наявній транзакції. Схема, ID, правила погодження, demo-only guard, заборона наповнення непорожньої БД та early return за dataset marker збережені.

Шість behavioral tests підтверджують створення наступного Task без колізії зі збереженням усіх восьми demo rows; незмінність Task та записів моделей, створених seed, при повторному seed; відсутність перемотування вже використаних ID; справжній HTTP preview/confirm і повтор receipt без дублю Task/AuditEvent; відмову seed на непорожній БД та у working profile. Assertions не підмінені перевіркою виклику helper або mock SQL.

## Цілісність evidence

Reviewer незалежно перевірив SHA ZIP проти збереженого GitHub artifact digest і upload digest у JOB_LOG.txt, усі чотири файли ZIP проти локальних байтів, три log SHA проти report.json.

| Артефакт | SHA256 |
|---|---|
| BoS_P10_002_CI_Raw.zip | 06cfb1a4f2ebae8767cd1340329c4a6405229d9493cc34cd46690048af4ce31f |
| report.json | 0a267aed2792f873debb872e31bdad41b33e498d6712e317b139cdc2d3165376 |
| postgres-before.log | dcf1ced527d9e4303369a681dc223519d38815042b8808387c8770a4df89fbb0 |
| postgres-after.log | 4728f1f909fad9472eef79ba9aea386a6842951652b1c5d110a18ba8f5f975e0 |
| sqlite-after.log | 62948fce34a6a94518711e4ec57515236d7ea98c67398c8c31a4cd6ed5fa7bd3 |

У runner `source_database_count=0`: це не доказ перевірки історичних БД; історичних БД у CI checkout не було. Усі виконані writes належать синтетичним disposable БД. `source_unchanged=true` узгоджується з незалежно перерахованим source digest.

## Межі та передача

1. Раніше наповнені старим кодом БД з dataset marker автоматично не ремонтуються. Повтор seed залишається no-op. VERIFIED стосується нового seed на виправленому коді.
2. Один CI run містив три вузькі фази. Full, повний postgres suite, E2E, інваріанти і повторні timeout експерименти не виконувалися. Старі P05/P06/full результати не переносяться на новий source.
3. P06-F02..F06 та A09/A10/A11 залишаються відкритими/обмеженими згідно з попереднім станом. Висновку про відсутність регресій у всьому застосунку немає.
4. Зберігається один кодовий commit без amend. Фінальні PROGRESS/READINESS/EXECUTION_STATE та цей review мають бути довготривало збережені окремим пакетом стану/evidence без копії коду. `docs_synced_to_git=false`; фактичне збереження пакета виконує головний агент і цим review ще не засвідчується.
5. Наступна рекомендована окрема картка: P10-003 для P06-F02, після нового повідомлення користувача та перевірки передумов. Автоматично її, P07 або будь-який full не запускати.

Reviewer виконав лише читання коду/логів та обчислення контрольних сум, написав цей огляд у власній теці. Додаткових застосункових тестів, CI, БД-операцій, remote actions або комітів не виконував. Блокувальних findings щодо самого виправлення fresh-seed немає.
