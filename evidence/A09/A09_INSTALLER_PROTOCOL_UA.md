# A09 · протокол нової окремої інсталяції

12.09.2026. Чернетка для інтеграції після A08. Усі створені тут компанії, файли й бази — нові синтетичні каталоги. Виробничих даних, мережевих завантажень або серверних запусків ці модулі не виконували.

## Розміщення та відповідальність

Оператор задає три розділені шляхи: незмінний вхідний пакет коду, довірений приватний реєстр інсталятора та відсутній каталог нової компанії. Реєстр не копіюється з клієнтського пакета й не лежить усередині компанії. Його запис означає фактичне створення конкретного каталогу та містить перевірену пару device/inode. Сам файл `INSTALLATION.json`, назва каталогу або UUID не є правом перезапису невідомої інсталяції.

| Шлях у bundle компанії | Призначення |
|---|---|
| `config/server.json` | Приватний JSON із canonical BOS_* env, унікальним UUID та секретом |
| `releases/<source_sha256>/` | Повна окрема копія перевіреного manifest пакета коду |
| `venv/` | Реальна нова Python venv без system site-packages; залежності лише з offline wheelhouse |
| `state/` | `BOS_INSTALLATION_ROOT`, приватний корінь стану цієї компанії |
| `state/data/bos.sqlite3` | Власна нова база, створена окремо та прив’язана до inode |
| `state/private/` | Приватні документи |
| `state/static/` | Статика, фактично зібрана collectstatic |
| `runtime-logs/` | Приватні журнали фактичних subprocess кроків |
| `INSTALLATION.json` | Версія/джерело та явний незавершений статус до повного приймання |

Код і state є сусідніми каталогами; чинний `server_config` не послаблюється. У кожної компанії власні source copy, venv, config, база та документи. Реєстр блокується справжнім POSIX advisory lock; паралельний процес отримує відмову. Windows locking/ACL ще не реалізовані й не прийняті.

## Фази

1. Read-only перевірка шляхів і пакета. Нова ціль має бути відсутньою; навіть порожній невідомий каталог не приймається. Вкладення у source, registry чи іншу інсталяцію, symlink/junction/UNC/`..` відхиляються.
2. Виключне створення root, запис ownership до приватного реєстру, незалежні UUID і `secrets.token_urlsafe(64)`. Нові каталоги мають 0700, контрольні файли — 0600. Не змінюються права попередніх шляхів.
3. Створення лише відомих config/state файлів. Повтор із тим самим UUID через той самий реєстр перевіряє root inode, версію, origin та точні раніше створені байти. Невідомий або змінений файл не перезаписується. Тести перерв після claim і config довели продовження без зміни ID/секрету.
4. Full manifest пакета перевіряє кожний шлях/SHA і повний склад файлів; DB/secret файли до code release не допускаються. Частковий власний release доповнюється тільки відсутніми файлами; змінений файл спричиняє відмову.
5. Реальна `python -m venv --copies`, `pip install --no-index --find-links ...`, `pip check` і перевірка кожної exact dependency через metadata нової venv. `PYTHONPATH`/`PYTHONHOME`/зовнішні BOS_* не успадковуються. Немає підміни нової venv на вже встановлені runtime-бібліотеки.
6. Canonical server validation, Django check, реальний migrate і collectstatic працюють тільки з own DB та `server_settings`. Окремий subprocess підтверджує actual SQLite, відсутність pending migrations, нуль бізнес-записів і наявний admin CSS. Демо не сіється.
7. Функція повертає `application_provisioned=true`, але `complete=false`, exit 2: справжні WSGI/TLS/health перевірки виконує наступний server runner. Bootstrap без wheelhouse також залишається incomplete. Відсутні wheels дають фактичну помилку pip і збережену власну часткову інсталяцію; це не успіх.

Підтримуваний runner погоджено окремим server-review: `python <release>/scripts/start_server.py --port <port>`, тільки loopback. Обгортка завантажує JSON у env і задає cwd release. Запуск runner/TLS до цього filesystem/provisioning набору не входив.

## Фактичні докази

- `a09_install_bootstrap_owned_lock.log`: 9/9 filesystem/registry тестів, 0,120 с. Перевірено existing/foreign/symlink/nested/root replacement, source version refusal, два унікальні UUID/secret/path sets, own partial resume, справжній competing-process lock і nonzero incomplete CLI без секрету у stdout/stderr.
- `a09_actual_install_1.json`: нова venv, 33 точні distributions включно з Waitress 3.0.2, pip check, canonical config, реальні A08 міграції та collectstatic, усі бізнес-таблиці порожні.
- `a09_actual_resume_2.json`: спочатку справжня відмова pip на порожньому wheelhouse до створення DB; потім та сама root/venv inode, UUID і config bytes успішно продовжені з offline wheels. Друга компанія має інші ID/secret/DB inode.
- Пакет цих перевірок: 261 файл, SHA `6269dca6458232f64dbe5180c8689d2627eadaaf5d7dc02f99ef5241149783a1`. Це заморожений синтетичний A08 working snapshot з A09 configuration draft, **не прийнятий реліз**. Оригінальний checkout або робочі SQLite не копіювалися як дані й не мігрувалися.

## Що ще не прийнято

Немає загального complete/install gate 8: WSGI, TLS, proxy, HTTP health та остаточний logger перевіряються root/іншим агентом. Після інтеграції всіх A09 файлів потрібно заново створити повний пакет, виконати canonical CLI та installation/HTTP tests на його точному SHA. Поточний `source_identity` metadata-only режим дозволяє тільки bootstrap; runtime вимагає повного `BOS_PACKAGE.json`.

Реєстр — довірений приватний адміністративний стан, а не захист від зловмисного адміністратора з повним записом до всіх каталогів. Аварія між першим mkdir і фіксацією ownership залишить невідому порожню ціль, яка відхиляється без видалення. Пошкоджений частковий контрольний файл також не перезаписується. Це межі безпечного повтору, не вигаданий автоматичний ремонт.

Перед використанням runtime повторно після `application_provisioned=true` потрібен явний start/update workflow: поточна чернетка спрямована на нову установку й продовження її незавершеного provision, не на оновлення живої компанії. Повне N→N+1/rollback залишається A09/A10. Виробничий server/domain/платні сервіси не створювалися.
