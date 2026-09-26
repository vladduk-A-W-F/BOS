# A09: 13 MiB — межу ще не прийнято

Стан: **НЕ ПРОЙДЕНО**. Жодна transport exception або відповідь 502 не зараховується як 413. Основний checkout не редагувався.

Фактичний початковий root-прогін: `evidence/A09/install-cli-after-1.json`, стадія `actual_https_contract`, `ConnectionResetError`. Нормалізований proxy log містив 413, але клієнт не отримав HTTP-відповідь, тому assertion залишається червоним.

Використано лише створену root синтетичну інсталяцію `/tmp/bos-install-check-2rctonft`; власні Popen handles запускали й зупиняли її supervisor. Лише health/readiness і завеликий запит; нових користувачів, документів, seed або migrations не створювали. Після кожної спроби hashes синтетичної SQLite та всього приватного дерева залишилися тотожними; supervisor завершився 0.

| Спроба після початкового root-прогону | Фактичний результат | Доказ |
|---|---|---|
| `Expect: 100-continue`, headers перед body | timeout, не прийнято | `tmp/A09_OVERSIZE_EXPECT_ACTUAL_1.json` |
| Паралельні надсилання body та читання response | HTTP **413**, TLS verified; 13 631 488 заявлено, 7 405 568 байтів надіслано до ранньої відмови | `tmp/A09_OVERSIZE_CONCURRENT_ACTUAL_2.json` |
| Точний candidate helper із фіксованим socket | HTTP **502**, TLS verified; assertion 413 провалено | `tmp/A09_OVERSIZE_CANDIDATE_ACTUAL_3.json` |

В останньому candidate використано саме початковий socket, щоб `HTTPConnection.send()` не міг автоматично відкрити нове з’єднання після раннього закриття response. Прогін показав 502, отже кандидат **не прийнятий**. `tmp/A09_EARLY_HTTP_RESPONSE.patch` та `tmp/server_http_checks_early_response.py` зберігаються лише для діагностики, не як green-виправлення.

Ліміт повторів був помилково порахований без початкового root-прогону: перевірка точного helper уже виконувалася, коли root уточнив сукупні три спроби. Це повідомлено root; подальших запитів не запускали. Не слід приховувати цю додаткову спробу.

Гіпотеза для наступної окремої задачі: рання відмова upstream і одночасне копіювання body через Caddy дають різні результати завершення з’єднання. У встановленому Waitress `parser.py` явно відхиляє `Content-Length >= max_request_body_size` ще під час заголовків. Це пояснює можливість раннього закриття; точну причину 502 окремо не доведено. Варто дослідити детерміновану відмову на межі proxy до передавання upstream та окремо підтримку streaming bodies. До цього gate не закривати, retry-loop або приймання 502/reset замість 413 не додавати.
