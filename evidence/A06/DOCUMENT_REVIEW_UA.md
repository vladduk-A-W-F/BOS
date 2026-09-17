A06 · незалежна вузька перевірка Document mutex

Виконано чотири нові тести з tmp/a06_document_mutex_tests.py на новій файловій SQLite 3.53.1: два red за контрактом порядку блокування, два green для спостережуваного міжкрокового порядку. PostgreSQL НЕ ЗАПУЩЕНО. Checkout не змінювався; реальні бази не читалися. SHA чотирьох operations/ERP файлів до/після збігаються.

| Тест | Факт до виправлення | Результат |
|---|---|---|
| upload lock order | Справжній multipart POST дав 201, створив версію B. Document read/INSERT відбулися без ERP mutex, INSERT поза atomic. | RED |
| review lock order | Справжній POST дав 200, змінив needs_review → approved. Document read/UPDATE без ERP mutex, UPDATE поза atomic. | RED |
| upload проти ship | ERP confirm після mutex, fingerprint і admission зупинено перед фактичним UPDATE Reservation. Upload дійшов до INSERT, але не закомітився під час паузи. ERP 200, upload 201; залишок/резерв 3, shipped 7, один shipment. Пізніший ship зі старим сертифікатом відхилений без другого руху. | GREEN на SQLite |
| review проти quality | ERP generic proposal має needs_review сертифікат; confirm після mutex/fingerprint зупинено перед actual admission SELECT. Review дійшов до UPDATE, commit під час паузи не відбувся. ERP 422 з повним rollback receipt/Inspection, review 200 після цього. Новий preview/confirm після review дозволив рівно одну Inspection. | GREEN на SQLite |

Два red доводять саме порушення прийнятого спільного lock-контракту на справжньому SQL. Вони не видаються за доведену втрату складу. Два concurrent green показують, що у цих контрольованих SQLite сценаріях загальне блокування запису вже запобігає Document commit всередині ERP-секції. Спостережувана пауза обмежена 0,5 с після реальної спроби SQL; червоний порядок блокування не замінюється цим позитивним часовим спостереженням.

Harness використовує TransactionTestCase, окремі connections двох workers, реальний login + CSRF та клонування тієї самої авторизованої сесії. execute_wrapper передає кожний початковий SQL рівно один раз. Пауза не змінює SQL/результат; факт завершення Document transaction фіксує on_commit. Таймаут, HTTP 500 і невідомі відповіді провалюють тест. Явний 409 Document допускає повтор після ERP; часткові записи не зараховуються.

Мінімальна продуктова правка: upload і document_review мають входити до transaction.atomic, брати чинний erp.service.write_lock, після очікування читати свіжі Policy/Document/current/checksum дані та виконувати INSERT/UPDATE у цій самій транзакції. errors має ловити конфлікт після виходу/rollback atomic. Парсинг нового файла можна лишити перед входом до критичної секції; жодного A08 storage/version redesign не потрібно.

На PostgreSQL цей mutex блокує рядок Configuration; прямий Document write іншої transaction без спільного mutex має окремий ризик. Реальний PostgreSQL прогін цих тестів ще потрібен. Жодного skip або твердження про успішний PG результат немає.

Докази: tmp/a06_document_mutex_before/test.log, чотири test_*.json із SQL/HTTP та tmp/a06_document_mutex_before/provenance.json з повною командою й SHA. Тести готові для перенесення root; PYTHONPATH має включати tmp до перенесення, settings — verification_settings, БД — новий check_<uuid>.sqlite3 з окремим BOS_TEST_MEDIA. Поточний запуск: 4 тести, 2 failures, 1,505 с. Готовність A06/gate 5 цим набором не оголошується.
