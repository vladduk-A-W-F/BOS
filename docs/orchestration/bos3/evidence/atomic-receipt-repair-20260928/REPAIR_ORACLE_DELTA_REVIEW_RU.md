# Незалежний delta review oracle B30-DEV8-ATOMIC-RECEIPT-REPAIR

Дата: 2026-09-28  
Режим: статичне читання. Python import, test, parser, runtime, HTTP, ACL,
DB і lifecycle не виконувалися.

## Перевірені bytes

* source repair без змін —
  `6483cc03bb7ea8fbf4e15a4b52c881b14ef0d8005cd0b16bafdf6455fa4c79da`;
* repaired oracle —
  `8b953ad4bfe8430e4da8e2b81c59105be116ae4364caf0b5d006409159264a1c`;
* manifest —
  `1c4ba522ae217aafb7c18d8bcc41d8f5392117a6f9a5ce00546d019e58ed7c8b`;
* report —
  `1d914f76c0caabd4539932ce244d58574fab8472540518e03fae76b8ca67d9a1`.

## Closure P1/P2

P1 закрито: fixture перед створенням перевіряє весь fixed chain від `D:\\`
до exact repair workspace через `lstat`, directory type та reparse/symlink
відмову. `TemporaryDirectory` створюється лише як child цього workspace;
cleanup викликається тільки для recorded fixture child і перевіряє його
видалення, не торкаючись parent або широкого D path.

P2 закрито: `test_one_winerror33_denial_reuses_temp_then_succeeds` прямо
покриває третій заявлений retryable Windows code. Existing cases як і раніше
перевіряють immediate success, winerror 5, persistent 32/три спроби із
збереженим target/temp і unrelated errors без retry.

Oracle лишається ізольованим: standard-library target import та monkeypatch
`os.replace`/`time.sleep`; без Django, owner instance, data/media, network,
lifecycle чи ACL write.

## Verdict

`ACCEPT_SCOPED_UNRUN_ISOLATED_ORACLE`.

Наступний крок можливий лише за окремим root decision: один exact focused
standard-library invocation для source/test hashes вище, raw stdout/stderr,
native exit і незалежний result review. Це не дає PASS до фактичного run,
не дозволяє official-start retry, candidate integration, recovery, HTTP або
window 2. Official start/window1 лишається `1/1`; same problem лишається
`1/3`.
