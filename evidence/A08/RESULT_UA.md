# A08 · приватні документи: локальний результат

12.09.2026. Версія 0.2.8-dev; база історії — commit 0ffe13ea83cad43f49b3d049f6bc401770b087ab. **Локальна SQLite-частина A08 завершена**, після незалежного огляду й повторного повного verify. Інвентар 85 шляхів / 12 місць не змінено; оцінка A08 лишається 3–5 людино-днів.

## Що змінено

Нові версії документів зберігають приватний незмінний оригінал із SHA-256 та точним розміром. Download, review і допуск документа до складських/версійних операцій звіряють фактичні байти. Прив’язаний відсутній або пошкоджений файл не маскується старим BLOB. Metadata не завантажує BLOB без потреби. Історичні байти, ID/FK, версії та права збережені.

Квота 1 GiB враховує всі фізичні файли MEDIA_ROOT і всі старі Document BLOB; один файл — до 10 MiB. Одночасні upload серіалізуються чинним ERP mutex. Після SQL-відмови прибирається лише власний новий незавершений файл; після commit право cleanup відкликане. Нові каталоги 0700 і файли 0600; старе media не chmod. Typed export зберігає приватність усіх вкладених каталогів.

Команда репетиції спершу створює свою окрему SQLite/media копію, збирає повний план, звіряє джерела і тільки потім переносить. План прив’язаний до конкретної копії. Неповні/пошкоджені записи відхиляють весь план. Старий BLOB не очищається; повтор не дублює файли. Restore виконується на ще одній новій копії. SHA legacy ChatFile без історичного checksum означає спостереження поточних байтів, а не доведену початкову справжність.

## До і після

| Доказ | Результат |
|---|---|
| REGRESSION_PLAN_UA.md; початкові integrity/ERP журнали |6 із 8 integrity методів червоні; окремий ERP метод відтворив 6 failed assertions на 3 шляхах. Після виправлень пройшли. |
| upload-recovered-before.log → recovered-after-1.log | Реальні upload/export відтворили 7 невдалих методів/10 assertions; після виправлення 43 цільові методи зелені. |
| A08_UPLOAD_INDEPENDENT_REVIEW_UA.md | Незалежно 12/12; паралельний upload, квота, SQL rollback, bound NULLsize і export modes. |
| canonical-migration-report.json; verify-2/sqlite-django-tests.log | Репетиція 45 таблиць:3 нові файли,0 при повторі, точне відновлення. Усі 9 міграційних методів пройшли, включно зі змішаними файлами, конфліктами, ownership, rollback і high-water. |
| verify-1-summary.json; GATE4_ISOLATION_UA.md | Перший fullverify зберіг 2 HTTP 500: зовнішня тестова atomic заважала durable upload. Oracle 201 не послаблено; ізоляцію перевіряльника виправлено. |
| gate 4-canonical-isolation.log; A08_ACCESS_HARNESS_REVIEW_UA.md | Справжні 201 CEO/manager, байти/SHA та commit; точний restore тестової БД й media. Чужий/підмінений owner і помилка після commit перевірені. |
| schema-check.log | makemigrations --check --dry-run: No changes detected. |

Кількості subset-запусків перекриваються. A08 додає 53 постійні методи до 325 A07: **378/378**, 134,922 с у повному наборі.

## Повний verify

Команда: `BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python PYTHONDONTWRITEBYTECODE=1 bash scripts/verify.sh --suite full --output evidence/A08/verify-2/report.json`. Загальний exit **1**, не прихований.

Початок: 2026-09-12T09:10:05.918142+00:00. Linux / Python 3.12.14 / Django 6.0.5 / DRF 3.17.1 / SQLite 3.53.1. Source SHA-256: `43cec951f09cd1801415a260484023d50b3355d7e9a1dd5ba407f4db1e88528f`; перед фіксацією збігається з поточним кодом.

SQLite: міграції; 151 функціональна + 5 launcher + 378 Django; 5×1000 інваріантів, 12012 складських кроків і 2485 replay; gate 4 **8370+9 HTTP**,183 URL,57 field methods; gate 5 **84/84** concurrency methods. Обидві оригінальні бази незмінні. Усі 11 критеріїв лишилися в report.

## Межі

PostgreSQL, Windows ACL і зовнішній CI не запускались. PG-ізоляцію committed HTTP цей helper не підміняє SQLite. Повний backup/restore установки, TLS, installer, upgrade N→N+1, браузер і клієнтське приймання лишаються наступними задачами. Критерії 6–10 ще не реалізовані; загальний verify не прийняв реліз.

Незгода з master: немає змін до прийнятих рішень. Важливо зберігати відмінність між доведеним локальним кроком і релізним прийманням — відсутні середовища не стають зеленими.
