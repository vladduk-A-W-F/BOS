# Пакет доказів невдалого вікна доставки dev.8

## Межа пакета

Це лише збережений, несекретний доказовий зріз картки
`B30-INVOICE-DEV8-D-DELIVERY`. Він не запускає застосунок, не виконує HTTP,
не відновлює процес і не змінює канонічне дерево, runtime, бази даних або
медіафайли.

## Зафіксований результат

- capture: native exit `0`;
- official stop: native exit `0`;
- apply: native exit `0`;
- official start: native exit `1`;
- post-start перевірка: `NOT_RUN`;
- root HTTP GET: `NOT_RUN`;
- дочірній процес і жива runtime-відповідь: `UNCONFIRMED`.

Згідно з `maintenance-receipt.json`, під час apply захищений payload не
змінився; змінені поля prepared-метаданих обмежені `source` та
`source_sha256`. Невдалий start не є доказом запущеного dev.8. Нова доставка
не прийнята. Історичний dev.7 також не є доказом поточної живої runtime.

Причина, описана незалежним failure review: official start завершився з
native exit `1` через `WinError 5` під час `os.replace(process.json)` у
`scripts/bos3_local.py:570`. Повтор, recovery, rollback, post-start або HTTP
перевірка цим пакетом не виконувалися.

## Склад і цілісність

У пакеті 33 явно відібраних файли: рішення та review, діагностика й
незалежний review невдалого start, фінальні maintenance / lifecycle /
post-start скрипти, фактичні вузькі delivery-результати, source-атестації та
обмежений набір owner archive, включно з `last-start-failure.json`. У каталозі
`delivery-once` фактично 12 файлів результатів і потоків; їх збережено всі,
щоб не створити неповний зріз.

Кожний файл звірено з відповідним джерелом за SHA-256 і довжиною байтів.
Повний перелік, хеші та шляхи provenance наведені у `MANIFEST.json`.

Навмисно виключено `owner-access.json`, `runtime-secrets.json`,
`prepared.before-stop.json`, бази даних, media та широкі native logs.

## Наступна межа

Пакет передається root для інтеграції та незалежному reviewer. Він не дає
статусу готовності, не підтверджує відновлення і не надає дозволу на наступну
операцію.
