# A08 · перенесення документів на власній копії

Підготовлено 12.09.2026. Це локальна SQLite репетиція, без production cutover або автоматичного редагування інсталяції.

## Файли для інтеграції

| Draft | Канонічний шлях | SHA-256 |
|---|---|---|
| `tmp/a08_document_migration.py` | `operations/document_migration.py` | `8314962b857f37af5cd87ac9a1699d9b703936e6b738bc43c29efbe18028b438` |
| `tmp/a08_check_document_migration.py` | `scripts/check_document_migration.py` | `0c1f820660c917c21a6bbce1271bd94efc06985d31b69674264d320679e02b14` |
| `tmp/a08_document_migration_tests.py` | `operations/test_document_migration.py` | `e6650fa36a38f453c799de6444e3656e52d3fcbf62d2c172fbff7dd1f21f0e00` |

Root інтегрує файли; агент не редагував checkout. Наведені 9 сценаріїв реально виконані через import overlay на нових копіях повного синтетичного A07 джерела. Канонічний Django test runner і fullverify після інтеграції ще має виконати root; ці результати їх не замінюють.

## Межі й поведінка

`python scripts/check_document_migration.py --source-db /absolute/copy.sqlite3 --source-media /absolute/copy-media --output-dir /absolute/new-rehearsal`

Вхід має бути явно наданою копією поза checkout. Output не існує, не міститься у source media та не містить `..`. Вхід відкривається read-only; SQLite backup API створює нову БД, а файли копіюються зі збереженням режимів приватних підкаталогів. Після фактичного створення DB/media видається capability поточного процесу. Перед записами перевіряються точний клас/registry, path/inode, Django NAME, фактична PRAGMA main та відсутність attached DB. Ім’я, env-прапорець або підроблений об’єкт не є дозволом.

Nullable A08 schema migrations застосовуються лише на власній копії. Перевіряються всі попередні рядки, IDs, applied timestamps історії міграцій і sequence high-water. Уже наявні A08 поля також порівнюються точно. `plan_migration` збирає всі виявлені конфлікти документів/архівних чатів у model/ID/reason. Невдала передперевірка зберігає `plan.json` і `report.json` з `complete=false`; CLI завершується ненульовим кодом без застосування документа. Читання не ремонтує байти/контрольні суми.

`apply_plan` зв’язаний із конкретною власною копією та працює в durable transaction під наявним ERP mutex. Створює приватні незмінні файли, зберігає original BLOB/text, status/access/version, ID/FK. Змінюються лише Document.original_file/size та спостережені ChatFile.checksum. Відсутність давньої checksum не означає доведену історичну автентичність; це явно записано. Видалення вже оголошеної checksum після складання плану блокує старий план. Помилка пізнього SQL trigger відкочує записи й очищає тільки власні незакомічені receipts. Повтор плану не створює нових ключів/файлів. ERP mutex revision є єдиною допустимою службовою зміною; за його відсутності перевіряється єдиний новий рядок, revision та ID/sequence.

Квота рахує всі фізичні файли та всі старі BLOB, включно з file-bound/архівними, плюс місце для повного перенесення. Копіювання байтів не звільняє старі BLOB. Відновлена нова копія перевіряється за всіма рядками, файлами, IDs і доступом. Окремий mixed тест виконує реальний A07 typed export/import усіх 45 таблиць та порівнює незалежний ORM snapshot і точні байти після читання.

## Фактичні сценарії та журнали

| Сценарій | Остаточний журнал | Результат |
|---|---|---|
| Mixed legacy/private/text/empty, repeat, restore, typed45 | `tmp/a08_case_mixed_2.log` | passed, 3 нові + 0 повторних файлів; 4 точні документи після restore/import |
| Усі конфлікти з model/ID, жодного застосування, refusal report | `tmp/a08_case_all_conflicts_2.log` | passed, 3 контрольовані findings |
| Late SQL trigger на другій прив’язці | `tmp/a08_case_rollback_1.log` | passed, рядки й файловий manifest незмінні |
| Forged/wrong DB/media/attached/cross-plan; nested/alias output | `tmp/a08_case_ownership_2.log` | passed, усі відмови до мутації джерела |
| Видалення відомої chat checksum після плану | `tmp/a08_case_chat_checksum_1.log` | passed, без автоматичного ремонту |
| Повна квота, включно зі старими BLOB | `tmp/a08_case_quota_1.log` | passed, 382 legacy bytes лишаються враховані |
| A07→A08 nullable schema, deleted-ID highwater | `tmp/a08_case_highwater_1.log` | passed, 400001/500001 збережені; фактичний наступний Document ID 400002 |
| Відсутній ERP mutex | `tmp/a08_case_missing_mutex_2.log` | passed, повна репетиція з 3 новими файлами та перевіреним єдиним новим службовим рядком |
| Bound missing/corrupt/null size без fallback | `tmp/a08_case_bound_conflicts_1.log` | passed, усі 3 ID відхилені |

Повний wrapper trial: `tmp/a08_migration_trial_3/report.json`, `tmp/a08_migration_trial_3.log`: 45 таблиць, 3 legacy documents, 1 archived chat, exact row preservation, replay 0, source unchanged, restore bytes/ID/access preserved. Свіжа перевірка wrapper з відсутнім mutex: `tmp/a08_case_missing_mutex_2/without-mutex/report.json`.

## Збережені невдалі спроби й виправлення

1. `tmp/a08_migration_trial_1.log`: harness не серіалізував datetime під час readonly snapshot до migrate. Типізоване представлення виправлено; trial 2 пройшов, trial 3 повторив репетицію після посилення plan/report.
2. `tmp/a08_case_mixed_1.log`: додатковий raw SQL oracle вимагав незмінного whitespace/key order JSON після типізованого A07 codec. Діагностика встановила тільки канонізацію JSON; manifests, sequences і файли вже збігалися. У цьому місці порівнюються незалежні ORM значення всіх полів, IDs, Decimal/JSON та manifests; raw exact oracle залишився для фізичного restore. Mixed 2 пройшов.
3. Незалежний review виявив можливе вкладення output у source media до запуску небезпечного рекурсивного copytree. Додано відмову до mkdir, включно з `..` alias. Реальний bounded negative тест підтвердив відсутність створеного каталогу і незмінність input. Небезпечний рекурсивний старий код не запускали заради red.

PostgreSQL і Windows не запускалися. Критерії 6–11 і product release цим контрактом не приймаються. Пакувати тільки код/журнали/JSON звіти; DB/media репетицій не додавати у Git чи user archive.
