# C01: незалежний review сумісності check_original

12.09.2026. Вузька перевірка одного тестового скрипта; без запусків, змін checkout або читання синтетичної чи початкової БД.

**Погоджено exact candidate. Блокерів у цьому виправленні немає.**

| Артефакт | SHA-256 |
|---|---|
| check_original_before.py | `1492577e808590bea1ad38fd3f689162ad6f975dfe42dc4a9a6c36591c593067` |
| check_original_after.py | `7c0cabd705511a6b2bbec76f529e0b63f518556e9f4a747bcef1887d09a70cfd` |
| full24-original-red.log | `f58cc27ee831202757e27e7ef4cf785aa94de613bb2c85d1a4c8b06708465e5c` |
| after.log | `9dee158c10bbee66939fd1474b7842b44f8a70e13cea0aa39305a7e56f971c93` |

Початковий actual red — AssertionError старого буквального `<dialog ref={dialog}`. C01 переніс діалог у ControlledTask, де фактично є `<dialog ref={ref} className="bos-dialog c01-dialog"`, showModal, onClose та onCancel. Topbar зберігає обробник Ctrl/Cmd+K і відкриває той самий ControlledTask. Нова source-перевірка відображає фактичну структуру, не вимагає повернення старого імені React ref. Це статичний доказ наявності; browser/keyboard end-to-end досі явно not_tested.

Порівняння AST з HEAD підтвердило буквальну рівність старих test labels. Старий цикл 12 маршрутів та всі решта старих test() збережені; їхній загальний passed залишається 32. Нова helper extra має такий самий виконуваний assert(condition,label) і додає label лише після успіху. Усі три виклики залишилися у тому самому безумовному потоці:

- quick task preview: фактичний POST preview повертає 200, потім його ID використовується confirm.
- task edit preview: фактичний POST preview повертає 200, потім підтвердження перевіряє persisted done.
- raw task bypass denied: фактичний POST без погодження повертає 403.

Жодна з цих умов не замінена константою, не вимкнена й не переміщена в невиконувану гілку. Actual after.log містить старі 32 labels, additional_passed=3 та саме ці три additional_checks. Копія скрипта у source/scripts/check_original.py має exact SHA candidate, що узгоджується з root actual isolated run. Лог не містить власного process-exit поля; exit0 наданий root як результат запуску. Повного verify тут не повторювали.

Виправлення змінює тільки check_original.py. verify/gate/count contract, UI, backend, бізнес-oracles і дані не послаблено. Це прийняття мінімальної compatibility адаптації, а не успішного full24: дві окремі історичні fixture помилки та full25 ще розглядаються окремо.
