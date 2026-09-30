# Незалежний result review: B30-INVOICE-DEV8-D window 1

Дата: 2026-09-28  
Режим: read-only review already saved evidence. Не виконувалися runtime/CIM,
HTTP, browser, тести, data writes, recovery або retry.

## Scope та raw evidence

Перевірено лише `delivery-once` і non-secret files archive
`maintenance-INVOICE-DEV8-D-20260928-window1`.

* capture result `E35B2D3D5664A1461B6256F8A4CF74228271DEC10D0B246EA6FA38CA22A30065`:
  одна invocation, native exit `0`, reviewed decision
  `C31171C399D8F6E5A60A00201A120FBE10BF21A730D3721BD951CAE9E5AEFDDE`,
  review `899E609721E2F5E3F59DDAC214A3E22874A89965388ACE31C9D4FB1433871F71`
  і maintenance script `dced1900...`;
* official-stop wrapper result `F6ECAABB73175F4560CA2CDE15DAC2A0D16859D6C3744485FD2BF12E35EB8812`:
  одна invocation, native exit `0`; archived official stop result
  `9428FFE1CCA878D5B5CAA28E4F8B2677CC60AF863D2DA26D9BA434428B856E4D`
  також має `NATIVE_EXIT_CAPTURED` / native exit `0`, а raw stdout
  `87D89B0662DBF5FB55C49398CCDE662B1B1B646BB1DD345EFF41F972C54B2B85`
  містить лише `stopped: true`, `persistent_data_retained: true`;
* apply result `2DF9806966EFEB388EAD8076BB378DB6B473CCD2BF6038E862DB1C883F74BABC`:
  одна invocation, native exit `0`; receipt
  `AE27326240082F501791008F9245D4E22EBE026D7E6077922E7244457F74F885`
  фіксує тільки `prepared.source` і `prepared.source_sha256`, п'ять exact
  candidate blobs та `protected_payload_unchanged: true`;
* official-start wrapper result `097D123B6C9F74853D24BDA94035AC3C7240FA52440C08A9AFE48C6F02E007B7`:
  одна invocation, native exit `1`; archived native result
  `209C07FFEAC6219318C39D555FC90FB1B35F95885A2E1CF19A1A6458024CE752`
  підтверджує `NATIVE_EXIT_CAPTURED` / `1`;
* archived start stderr `99D477BE088E54FE2F1FA01ECA3395C6716151520123BAB4D9969BA8134FA389`
  має `PermissionError: [WinError 5]` у `bos3_local.py:570` під час
  `os.replace(...process.json...tmp, ...process.json)`.

## Result disposition

`PARTIAL_WINDOW_FAILED_AT_OFFICIAL_START_NATIVE_EXIT_1`.

Фактично підтверджено лише capture/official stop/apply у межах exact window.
Apply receipt є доказом aggregate equality у цій phase, але не є доказом
поточного стану process/server після failed start. З native exit `1` не можна
стверджувати, що server зараз running, stopped або recovered. Post-start QA
і його єдиний HTTP GET не були виконані; delivery/readiness не прийняті.

Window failure rule застосовано коректно до наданого результату: після start
немає retry, recovery або HTTP evidence. Start failure є збереженим
actionable root cause для окремої статичної діагностики; ця review не дозволяє
виправлення, повторний start, rollback, kill чи іншу runtime action. Будь-яка
наступна дія потребує окремої картки, класифікації attempt і decision.
