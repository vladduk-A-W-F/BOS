# Незалежний final static review: wrapper P1 repairs

Дата: 2026-09-28  
Режим: static source/package review; wrapper execution, PowerShell parse, PG, app, lab та state actions не виконувалися.

## Exact frozen inputs

| Артефакт | SHA-256 |
| --- | --- |
| `staged/start-workday.ps1` | `c0c528c7bb0533ad490e07c9e21c259cd9d17e0952510896a0477bce249b6bbd` |
| `staged/bos-flow.ps1` | `f858fcba8d61ed72ab28f2ccfcee8ac90dc838e7f1a63278333bbe11ea8756ee` |
| `staged/bos.ps1` | `a47bd781490333e5145d4834d689b33b7633977f56bba5f9892192319492624d` |
| `MANIFEST.json` | `79ad21f23cce31eec8a04facd7b84a849cd915d389d31ace7b0d7097b77c5116` |
| `REPORT_RU.md` | `dd73dd26a4fe2ef4fd866cab76e2a219740edfabd4c4f99f63bc018cfbbd9e44` |

## Closure

1. Усі три wrappers замінили case-insensitive collision `[string]$Home` з automatic/read-only `$HOME` на `[Alias('Home')][string]$ControlHomePath`. Публічний `-Home` параметр збережено через alias, а selected value як і раніше передається тільки як Python `--home` до погодженого resolver/API.
2. `start-workday` зберігає `coordinatorStatusConfirmed`: unsupported home не доходить до app branch, а PG failure після підтвердженого coordinator status не скасовує незалежну legacy app flow. Це закриває P1 із `WRAPPERS_STATIC_REVIEW_RU.md`; раніший delta record лишається історією.
3. Жоден wrapper не додає second resolver, authority schema/marker, state bootstrap або D-home assumption. `bos.ps1` та `bos-flow.ps1` не запускають PG/lab/app до resolver-backed selected-home path у заявленому flow.

## Вердикт

`ACCEPT_SCOPED_STATIC_WRAPPERS_SOURCE_PREPARATION`.

Це прийняття тільки exact staged source/package repairs. Воно не доводить PowerShell parameter binding на цій машині, запуск wrapper, сумісність зовнішніх callers, authority establishment, cutover, registration, runtime readiness або dynamic behavior. Усі ці межі потребують окремих карток і доказів.
