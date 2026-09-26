# A10 — фінальна звірка backup/restore та операторського CLI

Дата: 12.09.2026. Checkout: `/workspace/sites/bos-original-refined`. Рецензент: `/root/a09_server_review`.

**Висновок: консенсус у перевірених межах Linux same-process maintenance, native backup, clean restore в нову установку та операторського CLI. Нових блокувальних дефектів у цих межах не виявлено. A10 загалом і готовність MVP НЕ ПРИЙНЯТІ.**

Це read-only звірка інтегрованих файлів, наявних фактичних доказів та документації. Нових перевірок, запусків або читань вихідних БД не виконували; checkout не редагували. CLI й виправлення stdin раніше підготував цей самий рецензент: поточний звіт є повторною перевіркою інтеграції та доказів, а не додатковим оглядом CLI іншим автором. Повний verify №19 під час огляду виконується; його результат не передбачається.

## Точні інтегровані версії

| Файл у checkout | SHA256 |
|---|---|
| `scripts/maintenance_server.py` | `0986f037cf99f9ada33e58716f40d8c407b415f039d936ce145e60215e12ebb5` |
| `scripts/managed_runtime.py` | `be7e26c107248ff3dc13d86acf700a9d84784f82df386b36d2e9e855ec181840` |
| `scripts/maintenance_control.py` | `4e9b33059b6faa7bb8a03a6dedecfc08d29493e0f0333fb231920c6e80714223` |
| `scripts/backup_server.py` | `27430b053bf714b09b89214278454144b6587040754f0db8d1d79f874e0cbed8` |
| `scripts/restore_server.py` | `baaf64239df69dd0a2c19bcab7b67044af3ad19cd9790f7d95e0b47f5b323eb0` |
| `scripts/generation_ledger.py` | `b68298be377367ae8bfcddd3ec44cfff446dcd9dc0698864a9a822ea6b8df3f1` |
| `scripts/start_server.py` | `f25b421aa9f5c2542ebecbe5cea3f6a70bad25d6bbfb8e27accbe01e3eced6c6` |
| `boss_project/test_maintenance_cli.py` | `ab2cde588f53674a47e811ae480c2d24eb452b6cdeca61c0b3cf6aa241c674a1` |

SHA відповідають раніше зафіксованим candidate і виправленням. Незмінні control/backup/restore/adapter SHA також прямо записані в канонічному gate 7 proof.

## Прийняті можливості та їхня підстава

**Керована зупинка.** Лише власні `Popen` handles, фактичний lifetime flock та живий owner у тому самому процесі. Lease видається після завершення writers/queue/workers/sockets і власних children без примусового kill. RLock утримується на весь capture; timeout не дозволяє копіювання. Same-N resume відкликає попередню lease до старту children та відмовляє за ACTIVE pointer. Це підтверджують збережені actual drain/control докази; вони не запускалися повторно.

**Backup.** Новий приватний destination поза installation/registry/code. Native SQLite, code/config/static, усі private files, зокрема orphan; schema/typed validation виконується code/Python активної owned release. Source hashes, inode та повноваження повторно звіряються. COMPLETE публікується після перевірок; виправлені API keys і marker failure paths мають збережений actual red → green.

**Restore.** Тільки target, відсутній до виклику; його створює ця сама операція. Перевіряється порожня нова DB і відсутність identities, використовується її власний inode під instance lock. Відновлюються точні native bytes та typed стан 45 таблиць, суми окремо за валютами, файли/code/static. Нова installation отримує нові UUID/secret/cookie namespace; stored users/roles/session rows/history збережені. Фінальна admission failure відкликає readiness до звільнення instance lock.

**Операторський CLI.** `backup` захоплює власну offline установку, перевіряє фактичний запуск, виконує quiesce/capture й залишає її зупиненою. `serve --control-stdin` приймає тільки status/backup/resume/stop у тому самому процесі; після backup потрібен явний resume. Помилка capture не запускає writers автоматично. `restore` не приймає force/overwrite/activation і прямо повертає scope даних/коду з `post_restore_http_verified=false`.

Stdin читається обмеженими блоками через select/os.read; потік явно join-иться, а owner перевіряє actual children/logging Event, поки очікує команду. У фінальному коді збережено strict fields/JSON parsing, server-generated command IDs і metadata allowlist. Raw config/password/worker errors або текст вхідної команди не серіалізуються як повідомлення помилки.

## Фактичні докази в репозиторії

`evidence/A10/A10_CLI_ACTUAL_RESULT.json` прив’язаний до **CLI `0986f037…`** і має **8/8**:

1. Offline backup та чиста зупинка.
2. Реальна foreground ready.
3. Stdin status у running.
4. Backup під живою quiescent lease.
5. Явний status quiescent із нульовою кількістю children.
6. Явний resume: generation 1 → 2, два власні children.
7. Stop із drain/close: `serve_exit_code=0`, `serve_stderr=""`, фінальна подія stopped/closed/complete=true.
8. Restore через CLI: native proof 45 таблиць і явний HTTP pending.

Окремі `A10_CLI_STDIN_SHUTDOWN_BEFORE.json` / `AFTER.json` зберігають причину попереднього падіння: daemon BufferedReader давав `_enter_buffered_busy`, exit −6. Виправлена версія дає exit 0, порожній stderr і завершений reader, **коли parent stdin pipe ще відкритий**. Закриття stdin батьком не використовувалося як обхід oracle.

`evidence/A10/verify-1/report.json` — **історичний завершений прогін**, source SHA `f53bf603d3548c33e636aa24643a2b77c893b96fd94c56787bca813f21e96896`, Linux/Python 3.12.14. Його не слід називати фінальною перевіркою нового stdin patch. Він підтверджує SQLite 151 + 5 + 440 та `source_databases_unchanged=true`; останню ознаку тут прочитано зі звіту, вихідні БД рецензент не відкривав.

Gate 7 цього прогону — **ПРОЙДЕНО, 10/10**. Прочитано відповідний `gate-07-sqlite.log`: нова три-валютна fixture EUR 17.39 / USD 123.45 / UAH 9801.07, actual original HTTPS, native capture, corrupt backup refusal, existing-target refusal без записів, new clean restore, original same-N resume, restored HTTPS login/exact document/version/new cookies, cleanup та late-admission negative. Capture і restore мають однаковий native DB SHA `adcc881441ca8d168f3e1e65902106d869313d17e6750dcc7f53b055b911bcb2`; private files — 2. Після нового входу session закономірно змінює DB, тому exact SHA перевіряється до входу.

## Блокувальні та відкриті межі

Нових блокерів локального capture/clean-restore/CLI scope немає. Проте загальний `complete` у прочитаному full report — **false**, і це правильно:

| Критерії | Фактичний стан verify-1 |
|---|---|
| 1, 2, 3, 5 | SQLite частина пройшла; обов’язкова PostgreSQL частина не запущена. |
| 4 | Пройдено. |
| 6 | Наскрізна звірка до копійки не реалізована. |
| 7 | Пройдено в наведених clean-restore межах. |
| 8 | Помилка: 13 MiB клієнт отримує ConnectionResetError, status null; records/private bytes незмінні. |
| 9 | N → N+1 / rollback не реалізовані. |
| 10 | Браузерний критерій не реалізований у цьому історичному report. |
| 11 | Реальний Windows runner не запущено. |

CI IDs відсутні. Заморожені 11 критеріїв не замінюються локальним CLI успіхом. Ledger прийнято тільки як current-owned/filesystem authority; наявність activation methods у модулі не є прийманням activation. Немає приймання generation switching, upgrade, rollback, power-loss recovery, довільного external daemon/IPC або Windows/PG deployment. Read-only backup hash verification сама по собі не робить довіреним сторонній package із виконуваним code.

## Документація та наступний checkpoint

`docs/BACKUP_RESTORE_UA.md` чесно описує new-target-only restore, нову identity, необхідний явний resume, HTTP pending у CLI та неприйняті A10/MVP/upgrade/rollback. `docs/SERVER_INSTALL_UA.md` зберігає A09 NOT ACCEPTED і точну причину 13 MiB failure.

Неблокувальна неузгодженість: рядок A10 у таблиці `docs/PROGRESS_UA.md` ще посилається на `evidence/A09/RESULT_UA.md` і називає CLI відкритим, тоді як верхній абзац уже повідомляє 8/8. Його слід узгодити після завершення поточного freeze/verify; доказів readiness це не додає.

Після завершення №19 потрібне звірення його фактичного source SHA і результатів, без перенесення припущень із verify-1. Цей звіт не запускає нових optional перевірок і не приймає A10 або MVP загалом.
