# Незалежний package review: archived control-home wrappers

Дата: 2026-09-28  
Режим: archive/control consistency only; staged sources, wrappers, runtime та tests не запускалися.

## Перевірений canonical archive

Canonical checkout: `D:/3/BOSDev/workspaces/bos3-canonical/repo` at `fdaff796f15fc81dfec3f58d49372a71a7940cf6`.

`evidence/control-home-source-20260928/wrappers/` містить рівно дев'ять expected files: card, manifest, report, три staged wrappers та три historical review records. Exact hashes збігаються з accepted inputs:

- staged `start-workday.ps1`: `c0c528c7bb0533ad490e07c9e21c259cd9d17e0952510896a0477bce249b6bbd`;
- staged `bos-flow.ps1`: `f858fcba8d61ed72ab28f2ccfcee8ac90dc838e7f1a63278333bbe11ea8756ee`;
- staged `bos.ps1`: `a47bd781490333e5145d4834d689b33b7633977f56bba5f9892192319492624d`;
- manifest: `79ad21f23cce31eec8a04facd7b84a849cd915d389d31ace7b0d7097b77c5116`;
- initial, delta та final review records: `1d94287c...`, `d959e9f5...`, `99d43fb7...` відповідно.

`CARD.json` є byte-identical WRAPPERS card. Historical findings та reviews збережені окремо, не перезаписані final review.

## Control consistency

Поточні зміни `ACTIVE_WORK_PLAN_RU.md`, `CONTROL_STATE.json` та `TEAM_CURRENT_RU.md` називають wrappers тільки `ACCEPT_SCOPED_STATIC..._INACTIVE`, зберігають обидва P1 як closed static-only history, та явно лишають live installation, tests, authority establishment, cutover і runtime gate відкритими. Вони не стверджують запуск wrapper, PowerShell binding, runtime availability або readiness.

## Вердикт

`ACCEPT_SCOPED_WRAPPERS_ARCHIVE_PACKAGE_INACTIVE`.

Root може архівно інтегрувати exact evidence/control records. Це не є дозволом встановити staged sources у live tools, запускати wrapper, виконувати тест або змінювати home/runtime/readiness.
