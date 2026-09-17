# A10 — незалежна перевірка backup draft

**Стан: вузький консенсус щодо виправленого worker і marker helper; повний capture/lease/restore ще НЕ ПРИЙНЯТО.** Реального capture під maintenance lease у цій перевірці не запускали; bool/mock lease не використовували. Основний checkout не змінювали, вихідні бази не читали. Окремі filesystem fault probes helper дозволені root і виконані лише на нових власних файлах; їх результати наведено наприкінці.

Дата: 12.09.2026. Файл: `tmp/a10_backup_draft/scripts/backup_server.py`.

Початковий SHA: `07c85f0b698ea94fcf5cd51bf1fdae118cbe95497fa2e1daf40ae552a995a101`.
Повторно прочитаний SHA після правок root: `836ee1e5bd27b73f87998f2903a93a425e999e5ba941c5f0c2aae97337c23d0a`.

## Підтверджені несумісності початкової версії

1. WORKER читав `fact['source_unchanged']`. Фактичний `scripts/reconcile_data.make_snapshot` повертає `source_main_unchanged` та `source_files_unchanged`; ключа `source_unchanged` немає. Після успішного snapshot цей код неминуче отримав би KeyError. Набори ключів окремо витягнуто AST без доступу до БД: `tmp/A10_BACKUP_REVIEW_FACTS.json`.
2. WORKER викликав `validate_snapshot(source, ...)` до `make_snapshot`. Фактичний `scripts/data_transfer._snapshot` приймає лише sealed snapshot і відхиляє наявність `-wal`, `-shm` або `-journal`; його SQLite connection використовує `mode=ro&immutable=1`. Передавання йому живого джерела суперечило контракту WAL-aware backup API.
3. COMPLETE створювався до фінального guard. Помилка після створення marker могла залишити каталог, який `inspect_backup` визнавав завершеним, хоча `capture_backup` завершився відмовою.

У повторно прочитаній версії **пункти 1 і 2 виправлені за кодом**: worker спочатку створює native SQLite snapshot, перевіряє лише цю sealed копію та використовує фактичний ключ `source_files_unchanged`. Під час повторної перевірки не заявляємо, що WAL-сценарій уже пройшов: потрібен реальний lease та фактичний запуск.

## Блокер завершення у проміжній версії — далі виправлений

Пункт 3 виправлено частково. Поточний try/except покриває лише `os.fsync(dir_fd)`. Виклики `installer.new_file(destination/'COMPLETE', ...)` і `os.open(destination, ...)` знаходяться **до try**.

Фактичний `scripts/install_server.new_file` виконує create → write → flush → fsync. Якщо fsync самого COMPLETE дасть OSError після запису всіх байтів, файл залишиться; обробник backup ще не активний. `inspect_backup` перевіряє наявність, канонічний вміст і hashes, тому такий marker може бути прийнятий після невдалого capture. Аналогічно не охоплена помилка відкриття каталогу після створення COMPLETE.

Потрібна вузька корекція: охопити одним обмеженим cleanup-протоколом створення marker, його fsync, відкриття/fsync каталогу та решту операцій, здатних впасти після появи marker. При відмові можна прибрати лише marker, який створено саме цим capture у новому приватному destination, з перевіркою його власності/inode; решту payload зберегти. Інший варіант — завершити всі ризикові читання/result hashes до фінального marker, залишивши один контрольований commit. Це рекомендація за читанням коду; fault injection без реального lease не проводили.

## Узгоджені частини поточного підходу

- Schema inspector і validate запускаються Python/code активної генерації через subprocess; coordinator не імпортує Django-моделі іншої версії.
- Зберігаються native SQLite, точні code/config/static та всі приватні файли, включно з порожніми каталогами. Вміст і metadata source повторно звіряються; read/write копіювання виконується у новий приватний destination.
- Source symlinks/спільні hardlinks/спеціальні файли відхиляються через installer path checks і inode/type/nlink checks.
- Вивід worker із приватними деталями не друкується як публічна помилка; повертається контрольований код відмови.
- MANIFEST містить явне `not_checked`; результат capture не видається за clean restore, post-restore HTTP, upgrade або rollback.
- `inspect_backup` правильно описаний як перевірка completeness/hashes, **не** як повноваження на відновлення цільової інсталяції. Самохешовані metadata не слід надалі перетворювати на authority без незалежного owned ledger.

## Неприйняті залежності та наступне фактичне приймання

Поточний backup викликає `lease.fenced_for(...)`. У прочитаному `tmp/a10_control_draft/scripts/maintenance_control.py` цієї реалізації ще не було; це pending integration. Потрібно реально утримувати supervisor owner RLock на весь capture та отримувати lease тільки після фактичного drain власного Waitress і завершення власних процесів. Сам факт доданого виклику `fenced_for` цього не доводить.

Реалізація `GenerationLedger/current_owned/assert_owned` у каталозі цього backup draft відсутня; її повноваження й активна генерація цим оглядом не прийняті. Повідомлена зупинка ledger agent через automatic content filter не є позитивним тестом чи дозволом ігнорувати ownership-перевірки.

AF_UNIX EPERM зафіксовано control agent; escalations або обхід обмеження не виконувались. Root готує фактичний in-process supervisor callback між drain/release. До отримання цієї живої lease-схеми й семантичних capture/inspect перевірок gate 7, backup, restore та A10 загалом залишаються неприйнятими.

Окрема майбутня перевірка стійкості до crash/power loss: наразі явно fsync-иться лише фінальний верхній каталог. Це не доказ durable directory entries кожного вкладеного code/private/static каталогу. У цьому bounded огляді crash-durability не заявляється і нові випробування не проводилися.

## Підсумкова повторна перевірка worker і marker

Фінально перевірений backup SHA256: `2b703cd0a7cb8a8e9f3254e827bc4a10955a6c17a25b798da68dad4c6b5eb9e7`.

Root переніс створення marker у `_seal_complete`: власний O_EXCL pending inode → запис/fsync → rename COMPLETE → fsync каталогу. Увесь post-create scope обробляється одним cleanup, який видаляє лише marker із власним inode. Result hashes обчислюються до публікації marker.

Окремий незалежний прогін `tmp/a10_backup_seal_probe.py` використовує **реальні** `_seal_complete`, `installer.new_file`, `inspect_backup` та власні нові тимчасові каталоги. Підміняються лише конкретні OS-виклики для відтворення I/O failures; business/lease/ledger логіка не підміняється й capture не запускається.

| Probe | Фактичний результат |
|---|---|
| File fsync EIO після запису marker | OSError; COMPLETE/PENDING відсутні; inspect_backup відхиляє; source незмінний. |
| Directory open EMFILE після rename | OSError; COMPLETE/PENDING відсутні; inspect_backup відхиляє; source незмінний. |
| Directory fsync EIO | OSError; COMPLETE/PENDING відсутні; inspect_backup відхиляє; source незмінний. |
| Позитивне завершення | Канонічний COMPLETE, без PENDING; inspect_backup приймає hash/payload fixture; source незмінний. |

Докази: `tmp/A10_BACKUP_SEAL_PROBES.json`, `tmp/A10_BACKUP_SEAL_PROBES.log`: **4/4**. Позитивний fixture перевіряє marker/payload integrity, не містить runtime capture й не видається за повну відновлювану інсталяцію.

Також прочитано фактичний звіт root `tmp/A10_BACKUP_WORKER_RESULT.json`: початковий KeyError відтворено реальним subprocess; виправлений versioned worker пройшов native snapshot і typed validation **45 таблиць /1 документа**, source files незмінні. Джерело — раніше створена власна A09 synthetic installation під exclusive instance lock. Це standalone worker proof, не підміна приймання live maintenance lease.

У відповідних перевірених межах три знайдені дефекти виправлені. Семантична інтеграція `fenced_for`, власність GenerationLedger, повний capture під фактичним supervisor lease, clean restore та A10/gates 7 і 9 залишаються окремими неприйнятими кроками.
