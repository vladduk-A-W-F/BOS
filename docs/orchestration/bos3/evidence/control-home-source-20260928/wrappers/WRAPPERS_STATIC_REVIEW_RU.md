# Незалежний static review: B30-D control-home wrappers source

Дата: 2026-09-28  
Режим: source/package review; PowerShell, Python, PG, app, lab, state та transport не запускалися.

## Перевірені inputs

| Артефакт | SHA-256 |
| --- | --- |
| `WRAPPERS_CARD.json` | `260502d04b3ca92984b7bc0b12debc48b13e52e9b73f0c4cc4b1602947ccbcfc` |
| `MANIFEST.json` | `b893eec8190d7eb987b9ede294f71a857a110c83dd3c133d1e04e5263cb5115a` |
| `staged/start-workday.ps1` | `67ca0d672140c7ca770749df522832b7700b61c41316d3a495ace28a0a29389e` |
| `staged/bos-flow.ps1` | `ac6f96fc6d910bf3558afc51a0fda2ab54be2b21ca5c279920ceb88d714cdb2c` |
| `staged/bos.ps1` | `e20e073bb3cc855b5af280a394bf7ad7e0804c36268485b4813fecf91c6e9f1a` |

## Підтверджене

- `bos.ps1` викликає fixed `bos_dev.py --home <selected>` до `pg-control` та lab, а tools source path не виводиться з `LOCALAPPDATA`.
- `bos-flow.ps1` лише передає `--home` до вже погодженого flow CLI; другого resolver, marker чи authority bootstrap не додає.
- `start-workday.ps1` викликає resolver-backed coordinator status до `pg-control Start` і PG status. Обгортки не інтерпретують D path самостійно.

## P1: app launch відбувається після відмови selected home

У `start-workday.ps1` coordinator status виконується на `:74`, а rejected nonlegacy home переходить у outer `catch`. Проте outer `finally` на `:102` запускає app branch за `$ownsMutex`; зокрема `Start-Process` на `:117` може виконатися незалежно від того, чи status resolver відмовив selected home.

Тому explicit unsupported home справді зупиняє PG (`:90`) і lab routes, але не гарантує відмову до app side effect, всупереч card/manifest invariant. Мінімальний repair: зберегти окремий позитивний факт успішного coordinator status та пропускати app stage при його відмові; app launch після успішного resolver status може лишитися незалежним від пізнішого PG outcome, щоб не змінювати ordinary legacy behavior ширше за потрібне.

## Вердикт

`NOT_READY_STATIC_P1_START_WORKDAY_APP_LAUNCH_AFTER_HOME_REFUSAL`.

Потрібен лише focused source repair та незалежний delta review. Це inactive partial preparation; wrapper registration, external callers, authority establishment, cutover і dynamic/lifecycle acceptance залишаються відкритими.
