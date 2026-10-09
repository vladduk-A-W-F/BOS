# Доставка owner-local локальною сесією Claude

Картку виконує сесія Claude на ПК власника.

**Дозвіл власника:** «ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ» (27.09) і «Переводи всю работу на себя все разрешаю ты главный теперь в проекте» (09.10.2026).

**Процедура** — кроки 2–9 `DEV10_INSTALL_UA.md`. Їх виконує інструмент `scripts/owner_local_delivery.py` з нової копії, а сервер запускає й зупиняє лише `bos3_local.py`.

**Заборонено:**
- init, seed, reset, flush, генерація пароля;
- зміна прав і запуск від адміністратора;
- видалення квитанцій процесу;
- автоматичні повтори.

Демо 1.0 не перемикати, ключі MCP не видавати. Секрети, паролі й рядки БД інструмент не виводить.

## Поточна доставка
- **Встановлено:** `9748b86`, версія `0.4.0-dev.1`, демо 1.0.
- **Ціль:** тег `v0.4.0-dev.2` — commit main із версією `0.4.0-dev.2`.
- **Міграції.** Інструмент застосує лише `connectors.0003_connector_url_kind`: вона змінює тільки стан Django, без SQL. Будь-яка інша міграція — відмова, потрібен окремий план.

## Як запускати
Кожен крок — одна команда з повними шляхами. Вона однаково працює в PowerShell і в Git Bash (його використовує Claude Code на Windows), змінні оболонки не потрібні.

Що підставити:
- `<Py>` — `D:/3/BOSDev/venv/Scripts/python.exe`;
- `<Root>` — `D:/3/BOSDev/local-bos3/owner`;
- `<Old>` — значення `source` із `<Root>/state/prepared.json`;
- `<New>` — нова копія поруч із `<Old>`, наприклад `<тека, де лежить Old>/BOS-v0.4.0-dev.2`, не всередині `<Root>`;
- `<Tool>` — `<Py> -X utf8 -B <New>/scripts/owner_local_delivery.py`.

Сесію Claude запускати в окремому робочому клоні, наприклад `D:/3/BOSDev/claude-work/BOS`, — не в `<Old>` і не в `<New>`.

## Кроки
1. **Нова копія.**
   - `git clone -c core.autocrlf=false https://github.com/vladduk-A-W-F/BOS.git <New>`;
   - потім `git -C <New> checkout --detach v0.4.0-dev.2`.
2. **Огляд, лише читання:** `<Tool> inspect --root <Root>`. Має бути `new_version` = `0.4.0-dev.2`, `new_clean` = `true`, а `installed_source` — це `<Old>`. Інакше стоп.
3. **Preflight, лише читання:** `<Tool> preflight --root <Root>`.
   - `running: true` і `preflight: PASS` — перейти до кроку 4.
   - `running: false` і `installed_pin: OK` (ПК перезавантажено, сервер не працює) — крок 4 пропустити.
   - Відмова «process is no longer running» — виконати `<Py> -X utf8 -B <Old>/scripts/bos3_local.py status --root <Root>`. Команда прибере застарілу квитанцію й покаже `exited`. Потім повторити крок 3.
   - `process_receipt: recovery_pending` у кроці 2 або будь-яка інша відмова — стоп і питання власнику.
4. **Зупинка:** `<Py> -X utf8 -B <Old>/scripts/bos3_local.py stop --root <Root>`. Очікується `stopped: true`.
5. **Резервна копія:** `<Tool> backup --root <Root>`.
   - Команда друкує шлях `<Backup>`. Це приватний каталог: доступ лише у власника й SYSTEM, перевірено.
   - Збій на цьому кроці нічого не змінює. Запустити `<Py> -X utf8 -B <Old>/scripts/bos3_local.py start --root <Root>` і написати звіт.
6. **Міграції:** `<Tool> migrate --root <Root> --backup <Backup>`. Очікується `applied: [connectors.0003_connector_url_kind]` і `data_unchanged: true`.
7. **Прив'язка:** `<Tool> bind --root <Root> --backup <Backup>`. Змінюються лише `source` і `source_sha256`.
8. **Старт:** `<Py> -X utf8 -B <New>/scripts/bos3_local.py start --root <Root>`.
9. **Перевірка** — одразу, ще до будь-якого входу: `<Tool> verify --root <Root> --backup <Backup>`. Очікується `result: PASS`, тобто:
   - версія на сторінці — `0.4.0-dev.2`;
   - csrf відповідає 200, MCP не відкритий: 404 без ключів (405, якщо власник видав ключ);
   - дані, пароль власника, media й приватні файли не змінилися.

   Вхід і читання підключених джерел зміною не вважаються.
10. **Власник** входить своїм логіном і бачить «Моніторинг» із бенто-плитками.

## Відновлення
Застосовується після будь-якої відмови після кроку 5 або результату FAIL у кроці 9:
1. Якщо сервер запущено — `<Py> -X utf8 -B <New>/scripts/bos3_local.py stop --root <Root>`. Якщо після невдалого старту лишилась квитанція в стані `recovery_pending` — стоп і питання власнику.
2. `<Tool> rollback --root <Root> --backup <Backup>`. Очікується `result: PASS`:
   - БД повернено з копії (копія → жива БД);
   - media повернено з копії, а замінені файли збережено в `<Backup>/media-replaced-…`;
   - `prepared.json` знову вказує на `<Old>` — через той самий ACL-безпечний `update_prepared_source`.
3. `<Py> -X utf8 -B <Old>/scripts/bos3_local.py start --root <Root>` і перевірити, що BoS відкривається.
4. Написати звіт. Успіх не оголошувати.

## Квитанція
`<Backup>/DELIVERY.json` — журнал кроків інструмента. Скопіювати його в `D:/3/BOSDev/qa-scratch/delivery-0.4.0-dev.2-<дата>/` разом із виводом кроків 1–4 і 8. У Git потрапляють лише посилання й SHA-256. Звіт власнику — до 10 рядків.
