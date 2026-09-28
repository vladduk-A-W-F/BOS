# Незалежний delta review B30-ATOMIC-RECEIPT-RECOVERY-PREP

Дата: 2026-09-28  
Режим: static read-only. Не виконувалися import/parser, test, Git/process/HTTP
probe, runtime/lifecycle або дані.

## Перевірені bytes

* source-prepare template —
  `58fdc28ded628c1824f283390abb82ed6a748e2b726c30b970357c282dede1fd`;
* official-start template —
  `b121fcf1de087d647b1a5612305fac053a6e3f5527dc98534bf1430bfb00f307`;
* post-start template —
  `846777b89e812fd4b30a5fadf838461ced522311c18c1cfdfa44dfd63282eb9b`;
* report —
  `4d05544fafec157a81542a9bc74de170c55f90c4fd8abda9bbb3a9476bda428d`;
* manifest —
  `bc9d486a6ad5546306aa347a4774fc8275a4bd65e75d36a5c25436e381318446`;
* dev9 source-only plan —
  `db9574d26a8389fcf713614b0895978df7dcf808e61c7ed1127f40273e34a407`.

## Закриття попередніх P1/P2

`preflight` після PENDING gate тепер звіряє actual `FAILED_SOURCE` через
clean Git HEAD `60f1...` і exact disk/tree digest `06a4...`; stale prepared
metadata сама по собі не проходить. `require_no_server_or_listener()` тепер
derive/verify-ить absolute native `%SystemRoot%\\System32\\WindowsPowerShell`
і передає subprocess-local native `PSMODULEPATH`, без PATH fallback.

`apply` повторно формує fresh preflight, вимагає direct-child receipt під
fixed scratch root, exact hash pinned final value та byte-for-field equality з
fresh observation. Це закриває declared reviewed-preflight handoff. Dev9 plan
має PENDING 40-hex target і не створює checkout чи runtime authority.

## Нові P1

**P1 — post-start HTTP 200 не зв'язано з exact ready process або committed HTML.**

`recovery_post_start_template.py` перевіряє лише apply receipt/prepared source
і `GET 200` на port 8030, потім друкує hash отриманого body. Воно не вимагає
identity-bound ready `process.json` receipt, exact listener PID/command/source
binding або exact expected normalized committed root HTML. Отже інший
відповідач на loopback може дати 200, а arbitrary response може бути записана
лише як hash без semantic equality. Мінімальний repair: повторно використати
або еквівалентно реалізувати dev8 `require_ready_receipt` process/listener
guard і порівняти єдиний response з exact versioned committed HTML; receipt
має вміщувати verified process identity та expected/served hashes.

**P1 — public post-start `--root` не fixed до owner instance.**

`verify(root, ...)` не вимагає `root.resolve() == INSTANCE_ROOT.resolve()`.
Він будує layout з caller-controlled root та перевіряє containment відносно
цього самого caller value. Мінімальний repair: перед layout відхилити будь-який
root, відмінний від fixed owner root, як це вже робить preflight/apply.

**P1 — aggregate baseline і post-GET preservation неповні.**

Recovery preflight/apply порівнюють лише freshly recomputed aggregate між
собою. Вони не зв'язують його з saved failed-window protected baseline
`dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1`, і не
вказують, чи recovery digest algorithm є byte-for-byte same scope. Отже
`protected_payload_unchanged` може чесно доводити тільки absence of changes
під час нового apply, але не збереження payload від failed window. Окремо
post-start обчислює aggregate лише до one GET, не після нього.

Мінімальний repair: read/validate saved failed-window baseline receipt та або
вимагати exact equality за тим самим algorithm, або явно зафіксувати і
перевірити обидві сумісні baseline scopes без перебільшення. У post-start
після єдиного GET ще раз обчислити той самий protected aggregate та residual
metadata; receipt має вимагати equality до apply/pre-GET і не виконувати
другий GET або DB query.

## Verdict

`NOT_READY_STATIC_P1_POST_START_IDENTITY_HTML_ROOT_AND_AGGREGATE_BOUNDARY`.

Попередні failed-source/native-PowerShell/preflight-receipt findings закриті,
але P1 у post-start унеможливлюють acceptance recovery package. Final dev9
passport/commit і root decision все ще PENDING. Жодного preflight, apply,
start, HTTP або recovery не схвалено; same problem лишається `2/3`, window1
start `1/1`.
