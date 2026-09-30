# Незалежний delta review: start-workday home-refusal repair

Дата: 2026-09-28  
Режим: static-only; PowerShell, coordinator, PG, app і lab не запускалися.

## Exact delta inputs

| Артефакт | SHA-256 |
| --- | --- |
| `staged/start-workday.ps1` | `ac041b1eca18af77561403d1f8d099bdde534f29b880d20c34578531c2d40637` |
| `MANIFEST.json` | `cecb94c3594564e289599bfe9c5ace4de58a0654f9268fe6f04b461fa7687e80` |
| `REPORT_RU.md` | `ce36c1b7245da42118036a772347e0048857b634656f1960de067c80146b95eb` |

## P1 closure

`$coordinatorStatusConfirmed` починається як `false` і стає `true` лише після успішного resolver-backed coordinator status та прийнятого task-count result. Outer `finally` виконує app branch тільки за умови одночасного mutex ownership і цього позитивного факту. Отже rejected/failed selected home не може дійти до `Get-Process`, registration lookup або `Start-Process`; receipt позначає app як `skipped_coordinator_status_not_confirmed`.

Факт не скидається при подальшому PG failure. Тому app branch залишається можливою після уже підтвердженого legacy coordinator status, що зберігає заявлену ordinary independent app behavior поза точним home-refusal repair. `bos.ps1` і `bos-flow.ps1` лишилися exact accepted bytes; manifest/report це чесно відображають.

## Вердикт

`ACCEPT_SCOPED_STATIC_WRAPPERS_HOME_REFUSAL_REPAIR`.

P1 із `WRAPPERS_STATIC_REVIEW_RU.md` закрито для staged wrappers. Це все ще inactive source preparation: wrapper registrations, external callers, authority establishment, cutover, dynamic validation і runtime/lifecycle acceptance не дозволені.
