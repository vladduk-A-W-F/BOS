# Незалежний static review B30-DEV8-ATOMIC-RECEIPT-REPAIR

Дата: 2026-09-28  
Режим: source/oracle review only. Не виконувалися Python import, test, parser,
runtime, HTTP, lifecycle, ACL, DB або network actions.

## Перевірені bytes

* картка `ATOMIC_RECEIPT_REPAIR_CARD.json` —
  `9d8849d0176c1dda7d0788df7a3c56e65d149d83ad4535b4c3ac6baf4fed5e25`;
* `scripts/bos3_local.py` —
  `6483cc03bb7ea8fbf4e15a4b52c881b14ef0d8005cd0b16bafdf6455fa4c79da`;
* `scripts/test_bos3_local_atomic.py` —
  `adbeb1d1ac27475e8331c0af39740950cfd9c711aaaba0aa46acb8881d01d2dd`;
* `MANIFEST.json` —
  `bf27e7e7894c7dce5f0c7d6e9094a18aa18d42159e93ea6a9ec5a027c3e710da`;
* author report —
  `a96e928f266e1247b45a6637a63b62a400ce5de7c58b647c3aebb7d0ac9e2aa2`.

## Результат source review

У `atomic_json()` збережено unique temp creation, exact JSON write, flush/fsync
та `os.replace`. Після write є рівно три спроби replacement: без затримки,
потім 50 мс і 100 мс. Повтор дозволено лише для `PermissionError` з
`winerror` 5, 32 або 33; третя така відмова та будь-який інший exception
поширюються. Temp не пересоздається, direct overwrite, ACL modification,
child creation, lifecycle action або cleanup не додаються.

Focused test використовує лише `TemporaryDirectory(dir='D:/')`, pure
standard-library import target та monkeypatch `os.replace`/`time.sleep`.
Він не створює owner instance, Django, database, network або lifecycle. Oracle
перевіряє exact JSON і single success, same-temp retry після winerror 5,
перманентний winerror 32 з трьома calls/збереженим old target і temp, а також
непов'язані exceptions без retry. Це є test preparation, не PASS.

## Findings

**P1 — fixture temp root не обмежений власним scratch subtree.**

`TemporaryDirectory(dir='D:/')` створює runtime fixture безпосередньо під
drive root, а не під виділеним
`D:\3\BOSDev\qa-scratch\bos3-atomic-receipt-repair-20260928`. Це порушує
контракт ізольованого allowlist і не фіксує, що cleanup торкається лише
власного test subtree. Мінімальний repair: зафіксувати absent/ordinary
non-reparse temp parent під цією scratch teкою, створювати кожну fixture лише
в ньому та перевірити cleanup виключно для власного дочірнього path. Не
додавати owner/runtime/ACL операцій.

**P2 — заявлений retryable код `33` не має прямого oracle case.**

Source перелічує `5, 32, 33`, але current four methods виконують success для
5, permanent denial для 32 і unrelated 87. Додати один synthetic `33` case
до існуючої focused oracle, щоб declared Windows sharing violation не лишалась
тільки неперевіреною гілкою. Це не потребує full suite.

## Verdict

`NOT_READY_FOR_ISOLATED_QA_P1_SCRATCH_CONTAINMENT`.

Сам bounded source repair не обходить ACL/lifecycle і коректно зберігає
історичний failure semantics. Але current unrun oracle не можна авторизувати,
доки P1 containment не виправлено. Після exact repair потрібен новий
static delta review; він не скидає `official start/window1 1/1` або
same-problem `1/3` і не дає дозволу на candidate integration, start retry,
recovery, HTTP, ACL change чи window 2.
