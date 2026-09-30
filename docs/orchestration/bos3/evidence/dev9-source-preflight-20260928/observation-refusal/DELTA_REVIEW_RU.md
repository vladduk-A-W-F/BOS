# Незалежний delta review: bounded observation recipe

Дата: 2026-09-28  
Режим: static/read-only; діагностичний child не запускався.

## Перевірені exact bytes

| Артефакт | SHA-256 |
| --- | --- |
| `observe_bos3_server_and_port8030_once.ps1` | `0598b04cfb911db5c87367d34c40a246227bee39c39e4731bb2f54002d40f4ce` |
| `ROOT_OBSERVATION_DECISION.json` | `47a9f2bdafd65a72ead667b9651ec52c6d943fbe0a5ea4a7a8fe9621ca8b2137` |

## Закриття delta

1. `New-Item` тепер використовує підтримуваний параметр `-Path`; каталог `observation1` все ще перевіряється як ordinary before/after створення і його наявність блокує повтор.
2. Child запускається через native PowerShell із `ReadToEndAsync` для обох потоків до очікування процесу. `WaitForExit(30000)` обмежує очікування child тридцятьма секундами.
3. Після child exit кожен drain має bounded `Wait(5000)`. При child timeout або stream-drain timeout створюється CreateNew receipt з exit/status unconfirmed; child не вбивається, raw streams не оголошуються збереженими, а створений evidence directory блокує retry.
4. `ROOT_OBSERVATION_DECISION.json` узгоджений із цими межами (`30000`/`5000`), має unbound script hash, `PENDING` reserved GO та явно забороняє lifecycle, preflight replay, apply, HTTP/socket, owner/DB доступ та автоматичне cleanup.

Залишкове обмеження свідоме: timeout не доводить, що child завершився або що runtime зайнятий. Це не дефект рецепта; receipt позначає такий стан як невизначений і не дозволяє follow-up дію.

## Вердикт

`ACCEPT_SCOPED_STATIC_BOUNDED_OBSERVATION_DELTA`.

Після root може заповнити лише reserved GO у цьому exact скрипті, звірити його final hash із decision і виконати не більше однієї read-only observation. Цей verdict не відкриває preflight, apply, start, GET, kill, recovery або зміну readiness.
