# A10 — незалежний огляд керованого обслуговування

Дата: 12.09.2026. Рецензент: `/root/a09_server_review`.

**Висновок: вузький консенсус для Linux same-process supervisor, його фактичного drain та адаптера BoS/HTTPS. Конкретних блокерів у цих межах не виявлено. A10 загалом не прийнята.**

Це read-only огляд коду та вже отриманих доказів. Checkout не змінювали, бази не відкривали, процеси не запускали. Окремий огляд capture/clean restore збережено в `tmp/A10_RESTORE_REVIEW_UA.md`.

## Перевірені версії

| Файл | SHA256 |
|---|---|
| `tmp/a10_inprocess_draft/scripts/maintenance_control.py` | `4e9b33059b6faa7bb8a03a6dedecfc08d29493e0f0333fb231920c6e80714223` |
| `tmp/a10_inprocess_draft/scripts/managed_runtime.py` | `85e9ad9d42af5b30cdef1d56f0f7fb8a9c0744ad614a8885b6fea77a10cb10f7` |
| `tmp/a10_drain_draft/start_server.py` | `f25b421aa9f5c2542ebecbe5cea3f6a70bad25d6bbfb8e27accbe01e3eced6c6` |

## Що підтверджує код

- Повноваження належать одному живому supervisor у тому самому процесі. Lease прив’язана до власника, PID, installation UUID, root/inode та operation UUID; стороння serialized ознака успіху не замінює цієї перевірки.
- Lifetime instance fence перевіряється за фактичним відкритим fd, inode та Linux `/proc/self/fdinfo` записом flock. Код не захоплює lock повторно для приховування втрати власності. Config bytes та inode власної DB повторно звіряються.
- Керування процесами відбувається через створені цим supervisor об’єкти `Popen`. Receipt drain приймається лише для власного Waitress handle і поточної generation: нуль активних/очікуючих робіт і workers, закриті sockets, Waitress 3.0.2. Сам receipt недостатній: потрібні також завершення власних процесів з кодом 0 та відсутність примусового kill.
- `lease.fenced_for` утримує owner RLock протягом усього callback; concurrent release не може відновити writers під час capture. Після release стара lease відкликається до старту нового child. Same-N resume відмовляє за наявності ACTIVE pointer.
- Адаптер запускає фактичну immutable release її Python; повторно використовує перевірені A09 loader/config, pinned Caddy, loopback profile і HTTPS health. Готовність потребує startup event власного Caddy, його живого handle та реального HTTPS. Обидва Caddy streams проходять нормалізацію; raw fallback відсутній.

## Фактичні докази

`tmp/A10_INPROCESS_CONTROL_RESULT.json`: **10 перевірок пройдено**. Прочитано також fixture та фактичний код адаптера. Докази охоплюють lifetime flock/іншого власника, реальний утримуваний WSGI write з HTTP 200 до lease, callback під fence, відхилення інших installation/root/operation, ACTIVE pointer, взаємне виключення concurrent release, same-N resume та відкликання старої lease, фактичне зовнішнє unlock fd, закриття owner і timeout.

Timeout фактично дає exit 6 без lease та без пізнього запису. Усі власні children зупинено; вихідну BoS fixture DB не змінено. Це не лише аналіз внутрішніх counters: runner раніше перевірено реальними held HTTP requests і фактичними commit у власні SQLite fixtures (`tmp/A10_DRAIN_ACTUAL_1.json`).

`tmp/A10_NATIVE_CAPTURE_RESULT.json`: окремі **8 фактичних сценаріїв** додатково підтверджують застосування цих же SHA control/adapter до BoS 0.2.10-dev: HTTPS login/document, quiescence/capture, same-N resume та відновлена установка з HTTPS. Деталі й межі restore наведені в окремому звіті.

## Межі консенсусу

Same-process callback явно дозволений root після зафіксованого AF_UNIX EPERM; IPC не запрацював і не видається за прийнятий. Нові IPC/control endpoints або обхід дозволів не створювалися. Linux `/proc` proof не є перевіркою Windows або довільної POSIX ОС.

Це керований foreground owner для довіреного локального coordinator. Огляд не приймає універсальне керування вже запущеним чужим daemon, інсталяцію системної служби, generation activation, upgrade, rollback, PostgreSQL, Windows або CI.

Заморожені 11 gates не змінюються. Відомий A09 oversized 13 MiB boundary залишається failed/blocked; нових спроб не виконували. Цей консенсус не перетворює A09 або A10 на повністю прийняті етапи.
