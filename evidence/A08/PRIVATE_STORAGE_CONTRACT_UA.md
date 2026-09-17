# A08 · контракт чернетки приватних файлів

Статус: окрема чернетка поза checkout. Новий модуль перевірено лише на синтетичних файлових каталогах Linux. A08, Windows, DB-інтеграцію, HTTP-права та повний verify цим результатом не прийнято. Усі справжні DB/MEDIA залишилися непрочитаними та незміненими.

## Файли

- `tmp/a08_private_storage.py` — чернетка майбутнього модуля, наприклад `operations/private_storage.py`.
- `tmp/a08_private_storage_tests.py` — 14 нових тестових методів із реальними файлами в `TemporaryDirectory`.
- `tmp/a08_private_storage_first.log` — перший запуск нового API, 14/14 green; це НЕ red-before-fix старого writer.
- `tmp/a08_private_storage_final.log` — повтор після додавання перевірки фактично записаних байтів, 14/14 green.

Тестовий процес не налаштовує Django DB та не викликає `legacy_blob_usage()`. Жодні бізнесові обчислення або фінансові функції не підмінялися. Portable filesystem branch викликаний без заміни його файлових операцій: справжні створення, читання, колізія O_EXCL та symlink refusal під Linux. Це не Windows acceptance.

## Інтерфейси для root

`PrivateDocumentStorage(root=None, quota_bytes=None)` читає `settings.MEDIA_ROOT` і `settings.BOS_DOCUMENT_QUOTA_BYTES` ліниво. Default quota — 1 GiB; можна явно встановити 0. Bool, від’ємне або невизначене значення не приймається. Це default конфігурації, а не виміряна клієнтська потреба.

`private_document_storage` — deconstructible singleton для Django FileField. План моделі від root:

```python
original_file = models.FileField(
    storage=private_document_storage, null=True, blank=True, max_length=255)
size = models.PositiveBigIntegerField(null=True, blank=True)
```

Сховище не робить model.save() і не видаляє/переписує старі поля. Викликати `document.original_file.save()` не можна: звичайні `Storage.save`, `_save`, `open`, `_open`, `url`, `path`, `delete` явно відмовляють. Керований upload присвоює готовий приватний ключ рядком.

```python
# Усередині чинного transaction.atomic + erp.service.write_lock(),
# після перевірки Policy, конфлікту code/revision і parse(file).
receipt = private_document_storage.save_verified(
    parsed['content'], parsed['checksum'],
    legacy_blob_bytes=lambda: legacy_blob_usage(using='default'))
# Root сам створює Document і потрібну подію:
# original_file=receipt.name, size=receipt.size, checksum=receipt.checksum.
# Для НОВОГО upload content=b''; інші parse-поля зберігаються як раніше.
```

- `save_verified(content, checksum, *, legacy_blob_bytes)` приймає bytes, bytearray, memoryview або binary stream з його поточної позиції. Повертає immutable `StoredDocument(name, size, checksum)`.
- `open_verified(name, checksum, expected_size=None)` повертає `BytesIO` тільки після перевірки всіх фактично відкритих байтів. Підходить для `FileResponse` після Policy. Буфер не зміниться від подальшого редагування файла на диску.
- `read_verified(...)` повертає bytes.
- `verified_document_bytes(document, storage=None)` підтримує `Document.original_file` і nullable `size`; тільки цей accessor вибирає перевірену legacy-форму.
- `usage(legacy_blob_bytes=...)` повертає фізичні байти, legacy BLOB байти, загальне використання і квоту.
- `legacy_blob_usage(using='default')` — lazy read-only `SUM(LENGTH(Document.content))` усіх рядків, без фільтрів і віднімання bound/archived записів. Переносимість фактичного запиту SQLite/PostgreSQL треба перевірити під час інтеграції.
- Помилки файлового вводу/виводу перетворюються на простий `PrivateFileError(ValueError)` українською. Відсутність — підклас `PrivateFileMissing`; текст не показує фізичні шляхи.

## Незмінність, SHA та квота

Новий ключ має тільки серверний UUID: `documents/ab/abcdef…32hex.blob`. Префікс ab має збігатися з першими двома hex-символами UUID. Імена від користувача не стають шляхами. Запис використовує exclusive O_EXCL, ніколи overwrite; колізія відмовляє. Файли створюються з mode 0600, приватні каталоги з 0700. Наявний POSIX корінь/каталог з іншими правами відмовляє; модуль не chmod-ить існуюче сховище. SHA має бути канонічним lowercase hex64.

Під час запису перевіряються streaming SHA, 10 MiB ліміт і доступні байти квоти. Після flush/fsync модуль повторно відкриває фактично записаний файл, перевіряє його розмір, streaming SHA та незмінність stat під час читання. Лише тоді повертає receipt. При невдалому збереженні видаляється тільки inode, який саме цей save щойно створив exclusively; існуючі файли не видаляються. Порожні створені підкаталоги можуть залишитися.

Фізична квота рахує ВСІ regular files усередині MEDIA_ROOT, зокрема сирітські та ChatFile; referenced-only фільтра немає. До них додаються ВСІ ще збережені Document.content BLOB. Якщо після перенесення BLOB лишився разом із файлом, обидві копії чесно займають квоту. Для великих історичних наборів може знадобитися явна більша конфігурація квоти; прихованого віднімання чи очищення BLOB немає.

Спільний ERP mutex обов’язковий навколо fresh legacy usage, quota check, файлового запису та DB-binding. Сховище не встановлює DB mutex самостійно і не обіцяє атомарність DB+filesystem без цієї інтеграції. `legacy_blob_bytes=0` припустиме тільки для фактично порожніх синтетичних даних або перевіреного нульового обсягу; stale cached total неприпустимий. Активні інші writers MEDIA_ROOT мають бути узгоджені з тим самим mutex. Відключений legacy chat503 цим модулем не активується.

Якщо файл успішно перевірено, але зовнішня DB-транзакція потім відкотилась, він може стати orphan. Він залишається незмінним і врахованим у квоті. Автоматичного видалення таких історично невідомих файлів немає. Root може додати окреме кероване очищення тільки щойно створеного file receipt з явним доказом відсутності binding; загального cleanup/delete API тут навмисно немає.

## Точне legacy-читання

1. Непорожній `original_file` завжди визначає джерело. Missing, invalid key, symlink, checksum conflict або неправильний `size` відмовляють. Навіть коректний legacy BLOB не використовується як fallback для зламаного bound file.
2. Для рядка без bound file непорожній BLOB має сам збігтися з SHA. При конфлікті text fallback заборонено.
3. Порожній BLOB з SHA(empty) повертає справжнє `b''`, навіть якщо text непорожній.
4. Для решти legacy-рядків допускається тільки exact UTF-8(text), SHA якого вже збігається зі збереженим checksum. Жодної нормалізації BOM, CRLF, пробілів, повторного парсингу або виправлення checksum.
5. `size=NULL` не вигадує історичного розміру. Для bound file non-NULL size звіряється з фізичним файлом; новий upload має записувати фактичний size.

## Сумісність із A07 і межі інтеграції

- FileField key зберігається відносно MEDIA_ROOT, тож чинний A07 media_manifest переносить і звіряє його без виклику Storage.path/url.
- Root має додати schema descriptor `file_size_column` для `operations.Document.original_file`, коли поле size доступне в ProjectState. Null size не можна перетворювати на int до рішення про legacy перевірку.
- Для A08 перевірка backup/preflight має також звіряти Document.checksum із фактичним media SHA; загальний A07 manifest сам по собі гарантує незмінність копії, а не історичну правильність checksum документа. Nullable ChatFile.checksum потребує окремого явного статусу «ще не звірено».
- Зміни моделей, міграцій, HTTP, version uniqueness, аудиту, UI й існуючих fixture не внесено. Їх інтегрує root після A07.
- Пряме збереження FileField у стандартному Django admin відмовить; адміністративний шлях має використовувати керований upload або бути readonly. У відповідях API не потрібно повертати storage key/path.

POSIX реалізація тримає anchored dir_fd, O_NOFOLLOW, окремо перевіряє кожний ancestor, regular file, відсутність hardlink для документа та зміни stat. Portable fallback перевіряє всі компоненти is_symlink/is_junction, канонічні server-generated keys і exclusive open; читає тільки фактично відкриті байти в перевірений buffer. Він розрахований на довірений приватний каталог службового користувача. Захист від процесу з довільним записом у серверну файлову систему не є заявленим контрактом. Windows ACL/junction/race та запуск Python 3.15 — НЕ ЗАПУЩЕНО, залишаються A11; ctypes ACL і платформи/сервіси не додавалися.

## Фактична перевірка

Команда (Linux, Python 3.12.14):

```bash
PYTHONPATH=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python /workspace/scratch/c7b51e996a9f/tmp/a08_private_storage_tests.py
```

Фінальний результат: `Ran 14 tests` → `OK`. Перевірено binary/empty/UTF-8, exact 10 MiB/+1, квоту з orphan+BLOB, відмову при unknown quota, перерваний потік, некоректний SHA, immutable buffer, legacy fallback правила, missing/corrupt bound файли, traversal, root/ancestor/final symlink, hardlink, FIFO, exclusive collision, заборону raw URL/open/write/delete і POSIX права. DB aggregate, migrations, HTTP, міжпроцесний mutex, PostgreSQL та Windows цим запуском не перевірялися.
