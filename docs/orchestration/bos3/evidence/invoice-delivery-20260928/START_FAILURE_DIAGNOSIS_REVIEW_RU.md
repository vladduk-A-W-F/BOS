# Незалежний review форензики B30-INVOICE-DEV8-D start failure

Дата: 2026-09-28  
Режим: статичне читання saved evidence та exact source. Не виконувалися
process/runtime/HTTP/ACL/file probes, start/stop/retry, тести або зміни даних.

## Перевірений input

`START_FAILURE_DIAGNOSIS_RU.md` має SHA-256
`dcab61e6f7d1e89c8d40ca383b6b968b3caeffa964b2c3014874c5ad7292010c`.
Звірено з exact source start path і попереднім result review
`DELIVERY_ATTEMPT1_FAILURE_REVIEW_RU.md`.

## Verdict форензики

`ACCEPT_SCOPED_FAILURE_BOUNDARY_WITH_CAUSE_UNCONFIRMED`.

Діагноз коректно розділяє встановлене від невстановленого:

* saved stderr доводить `WinError 5` на parent-side `os.replace` temporary
  `process.json` у start line 570 після запису `identity_recorded`;
* exact source доводить, що internal child пише `launch-<id>.json`, читає
  `process.json`, але не є його writer; parent writer race не встановлено;
* saved `last-start-failure.json` описує historical identity-verified cleanup
  child, а не current PID/listener/liveness;
* ні holder file lock, ні ACL, driver або інший actor не ідентифіковані.

Тому native exit `1` лишається фактом failed start. Діагноз не є доказом, що
runtime зараз stopped, running або recovered, і не робить доступним retry.

## Допустима наступна діагностична картка

Можлива окрема `READ_ONLY_START_REPLACEMENT_METADATA` картка з єдиною
першопричиною: відмежувати persistent path/ACL defect від невстановленої
transient file-sharing denial. Її allowlist має обмежуватися:

1. metadata-only `lstat`/attributes/reparse/type/length/mtime для
   `owner/state`, `process.json`, двох recorded `process.json.*.tmp` та
   `last-start-failure.json`;
2. read-only owner/DACL/inheritance/SDDL inspection саме цих parent/file paths,
   без зміни ACL, ownership або handles;
3. static read exact `atomic_json` і Windows replace/file-sharing contract.

Виключення: вміст secrets/access files, data/media, будь-який process/CIM
query, handle/lock enumeration, HTTP, status/start/stop/kill, retry, cleanup,
ACL change та synthetic/runtime reproduction. Таке читання може виявити лише
стійку path або ACL невідповідність; воно не може заднім числом довести
transient holder.

Це не повна attempt і не скидає історію. Будь-який synthetic repro або новий
official start належить до тієї самої проблеми `process.json` replacement,
має успадкувати вже спожиту start attempt `1` і потребує окремої класифікації,
allowlist та explicit root decision. Ніякого повтору не схвалено цим review.
