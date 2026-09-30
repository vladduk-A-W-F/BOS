# Незалежний static delta review: post-start та план джерела dev9

Дата: 2026-09-28  
Режим: лише читання; виконання не проводилося.

## Перевірені входи

| Артефакт | SHA-256 |
| --- | --- |
| `recovery_post_start_template.py` | `545174920850e8197589b5377a5d9a740aaad3734108fbac3a032445a0f62fd8` |
| `recovery_source_prepare_template.py` | `58fdc28ded628c1824f283390abb82ed6a748e2b726c30b970357c282dede1fd` |
| `recovery_official_start_native_exit_template.ps1` | `b121fcf1de087d647b1a5612305fac053a6e3f5527dc98534bf1430bfb00f307` |
| `MANIFEST.json` | `a18c10a5059c7d725a1d372d4171dfd553801973898fdab5c200ee4d8d98b6e8` |
| `IMMUTABLE_DEV9_SOURCE_PLAN_RU.md` | `db9574d26a8389fcf713614b0895978df7dcf808e61c7ed1127f40273e34a407` |

## Закриття P1 post-start

Виправлений post-start шаблон закриває знайдену раніше межу доказу.

1. До читання owner/state даних він відхиляє будь-які `root` і `repaired_source`, що лексично не дорівнюють зафіксованим `INSTANCE_ROOT` та `REPAIRED_SOURCE`; далі обидва шляхи проходять ordinary/no-reparse перевірку.
2. Приймається тільки `NATIVE_EXIT_CAPTURED` з `native_exit: 0` і точними root, source, commit та digest. Окремо перевіряються ready receipt, PID, creation ticks, образ Python, повний command-line token set та єдиний loopback listener на `8030` з тим самим PID.
3. Єдиний direct loopback GET без proxy, cookie, redirect і повтору звіряє HTTP 200 з нормалізованим exact committed `frontend/boss_app_html.html`; єдина дозволена підстановка -- token версії dev9.
4. До GET і після нього застосовується той самий digest protected payload. До-GEТ значення повинне збігтися одночасно з архівованим failed-window baseline `dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1` та apply receipt; після GET воно мусить лишитися тим самим, як і residual metadata.

Це є доказом лише контракту майбутнього receipt. Воно не доводить live Windows lock holder, успішний start, фактичний HTML-відповідь чи готовність продукту.

## План підготовки джерела dev9

`IMMUTABLE_DEV9_SOURCE_PLAN_RU.md` коректно лишається планом без виконання: фіксує один можливий shared/no-checkout clone та один detached checkout з pending immutable 40-hex target, чистими ordinary/no-reparse контролями, process-local Git environment і receipt-умовами. Він не надає права на clone, checkout, підготовку runtime, rebind, start або post-start GET. Перед будь-яким виконанням потрібні незмінний candidate/pin, окремий static review їх відповідності та чинне root-рішення.

## Вердикт

`ACCEPT_SCOPED_STATIC_POST_START_REPAIR` для наведеного шаблону.

`ACCEPT_SCOPED_DEV9_SOURCE_ONLY_PLAN` для плану джерела.

Це не є дозволом виконувати recovery або source plan. Ліміти залишаються: historical start `1/3`, window `1/1`, same-problem `2/3`; жоден readiness прапорець не змінюється.
