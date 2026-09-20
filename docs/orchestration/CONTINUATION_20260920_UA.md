# Продовження BoS: точний кандидат і межі доказів

Стан пакета: **DOCS_ONLY_READY_FOR_INDEPENDENT_REVIEW**. Дата створення: 2026-09-20T17:33:42.480912+00:00. Це зведення не є новим прогоном застосунку, БД, браузера або CI.

База патча `646d3b80597e087a1ada14221024ec40588996f0`, tree `1b0bf4e03a4e506d76f2d264e173d1bdc23e7fd3`. Frozen checkout `D:/3/Codex/2026-09-20/bos-execution/work/continuation-focus-frozen-20260920`; normalized runtime SHA256 `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`. Focus-freeze receipt порівняв1988 tracked files;1843 текстові відмінності були CRLF/LF, інші байти, включно PDF, точні. Попередні commit `530043a80c1196dfcd7bc8bef73b2ec041c09a68`, tree `4f7bb2cfe70cbb95f835e58be5ab1e690e3b8122`, runtime `dae72739e3a4a260d23db5259066636b01258de4093f457537df35292cd892a6` та їх freeze збережено. Source/receipt hashes перевіряються окремо; raw logs не нормалізуються.

Опублікований head у збереженому PR observation17:00:48UTC — `3d979060fe9862119ba8ad6c9d8bd505103796e3`. Одинадцять комітів нижче локальні; remote mutation не виконувалась. Публікацію веде призначений інтегратор. Нові зміни після бази потребують reconciliation; цей patch не є доказом нових bytes або PR2.

**Root ACCEPT_SCOPED на646d3b8/98b011:** actual attempt5 exit0, Gate10 7/7; окремі transfer/payment/replay/document flows3/3;26 артефактів перевірено за SHA і bytes. Постійний working-mode стенд [локального перегляду](http://127.0.0.1:8876/) також прийнято; сервер залишено працювати за receipt, root підтвердив publicHTTP200. Звіт: [BoS-browser-demo-acceptance.md](C:/Users/user/Documents/Codex/2026-09-20/realtime-voice-chat/outputs/BoS-browser-demo-acceptance.md); інструкція: [LOCAL_REVIEW_RU.md](D:/3/Codex/2026-09-20/bos-execution/work/continuation-evidence-20260920/LOCAL_REVIEW_RU.md). Це завершені scoped приймання, а не наступні невиконані задачі.

| Коміт | Картка | Raw / exit і межа перевірки | Незалежний статус |
|---|---|---|---|
| `811a613` | S1-CONFIRM-RECOVERY | 22 controlled actual JSX/global fetch cases; build and lexical PASS in saved raw. No browser/DOM/DB proof. Source was subsequently extended by FLOW and DOC UI. | ACCEPT_SCOPED_RECORDED_BY_COORDINATOR |
| `90e2cf8` | PLAN-DOC-MATCH-CONTRACT | 18 pure unit tests, exit0. Synthetic one-line/full-PO only; no authorization proof, posting, persisted exception queue, AI or OCR in pure contract. | ACCEPT_SCOPED_MOCK_CONTRACT_RECORDED |
| `92d0713` | SUPPLY-OPTIONS-READ | 12 SQLite tests, exit0. Initial finding withdrawn: OrderCancellation is in extended MODELS. write_revision is an additional barrier; no demonstrated old cancellation race fixed. | ACCEPT_SCOPED_SQLITE12 |
| `ae10e3f` | FLOW-ORDER-SETTLEMENT | Historical 17/18 then18/18 then policy1/1 apply to older hashes. Real raw-reference P2 fixed. Final accepted bytes have two relevant PASS cases inside mixed7 run with overall exit1; intermediate2-test exit0 uses different source hashes. | ACCEPT_SCOPED_REFERENCE_FIX |
| `67cc588` | DOC-MATCH-SERVER | Final24 SQLite tests exit0. First24 also exit0 but private parser diagnostic was found and fixed before final source. Final raw read:41 SELECT queries, bytes/source unchanged, no business writes. Dedicated independently signed hash-verdict is not in this folder; chief coordination records scoped acceptance. | ACCEPT_SCOPED_RECORDED_BY_COORDINATOR |
| `bfbc588` | FLOW-READ-UI | Mixed7 tests overall exit1:6 pass/1 route-fixture error. Fixed fixture1/1 exit0, not a green full rerun. Eight controlled cases precede currency override fix; later focused actual-dialog UAH/EUR/USD check, build/lexical accepted. Current shared sources later extended by DOC UI. | ACCEPT_SCOPED_RECORDED_BY_COORDINATOR |
| `bc6cc57` | LOCAL-REVIEW-SUPPORT | Historical support receipt:16 mock controls exit0 and actual Windows stdlib-only process proof. Public CSRF readiness and durable process ownership corrected. The accepted running demo is separately bound to646d3b8. | ACCEPT_SCOPED_SUPPORT_ONLY |
| `accbedc` | DOC-MATCH-READ-UI | 4 HTTP tests exit0, followed by test-only local fixture import change and1 targeted PASS. 5 controlled JSX cases PASS after first whitespace assertion failure. Discovery9/9 is not execution. No approval or posting; operation_proposal null. | ACCEPT_SCOPED_DOC_READ_UI |
| `23f7145` | FLOW-BROWSER-HELPER | Final9 mock/oracle controls exit0; initial8 failed cleanup, then8 PASS, then actual refresh correction9PASS. Actual transfer/payment replay and ordinary-document exception subsequently accepted in attempt5 on646d3b8; this unit receipt remains historical. | ACCEPT_SCOPED_HELPER_ONLY |
| `530043a` | UI-LOCAL-RUNNER | 12 mock boundary/evidence controls exit0 plus actual Windows stdlib-only ownership proof. Not Gate10. Seed/migrate interruption cleanup is outside this card. Unknown child exit preserves owned runtime; no PID-only delete/stop. | ACCEPT_SCOPED_RUNNER_ONLY |
| `646d3b8` | WORKPOINT-DIALOG-FOCUS | Controlled before exit1; after4PASS exit0; recovery22PASS exit0; build exit0. Chief independently accepted focus sources, then actual browser attempt5 exit0/Gate10 7 of7 and separate bounded flows3 of3 on this exact commit. | ACCEPT_SCOPED_FOCUS_AND_ACTUAL_BROWSER |

Source→receipt→raw→review з точними SHA256 та bytes: [EVIDENCE_INDEX.json](D:/3/BOSDev/handoffs/execution-writer-20260920/EVIDENCE_INDEX.json). Readiness packet: [READINESS_PACKET_RU.md](D:/3/BOSDev/handoffs/execution-writer-20260920/READINESS_PACKET_RU.md). Це локальні handoff-артефакти, не опубліковані GitHub докази. Карточки, у яких авторський статус ще pending, не переписані: пізніший verdict посилається на окремий незалежний звіт або збережений статус головного.

## Історія, яку не можна згорнути в загальний PASS

- S3 sqlite-1:10PASS. sqlite-2:12 tests із двома невдалими підвипадками одного тесту через хибну передумову reviewer. sqlite-3:12PASS, exit0. Finding про cancellation відкликано; write revision — додатковий бар'єр.
- Settlement:17/18 →18/18 → окремий policy1/1 стосуються старих hashes. Raw-reference P2 виправлений; проміжні2PASS мають інші hashes. Для фінальних accepted bytes два relevant methods PASS у mixed7 run, але весь run exit1 через route fixture. Після fixture fix лише1 targeted route PASS; повного зеленого повтору немає.
- FLOW controlled8PASS були до currency correction; окремий focused UAH/EUR/USD actual-dialog case підтверджує саме зміну. Shared frontend пізніше розширено DOC UI/focusfix. Старі receipts лишаються на своїх commits. Focusfix окремо має4PASS і новий recovery22PASS; єдиного22+8+5 прогону не заявлено.
- DOC server перший24PASS мав небажаний parser diagnostic; після виправлення інші source bytes і фінальний24PASS. DOC UI4HTTPPASS, потім test-only import fix і1targetedPASS;5controlledPASS після збереженої assertion-помилки. Discovery9/9 означає лише discovery.
- Runner12 mock controls і actual Windows stdlib proof не є Gate10. Попередні browser attempts1–3 incomplete; старий server_stopped=true не доводив child exit. Пізніша read-only reconciliation доводить лише відсутність matching processes/listeners на час спостереження.
- Historical Gate4 e66af: fixture HTTP422 до route sweep (не «до будь-якого HTTP»), exit1; PG fresh migration exit0, SQLite original exit невідомий після observer cleanup error. Access-current-1 має checks=[] і не має final receipt: INCOMPLETE; його не відновлювати з цієї картки.

## Усі одинадцять критеріїв

| № | Незмінна вимога | Статус для frozen candidate |
|---|---|---|
| 1 | Міграції на порожніх SQLite і PostgreSQL | INCOMPLETE_CURRENT_CANDIDATE — Historical e66af PG16 fresh migration exit0; SQLite original exit unknown after observer cleanup error. Current frozen candidate not rerun. |
| 2 | 151 функціональна + 5 launcher + решта тестів на обох СУБД | NOT_ACCEPTED_CURRENT_CANDIDATE — Scoped new tests and historical CI do not replace both-DB acceptance. PG new-read preflight made0 test attempts: port55439 unavailable and SQLite-only fixture guard. Separate fixture correction has2 SQLite PASS; not PG PASS. |
| 3 | П’ять інваріантів, мінімум 1000 випадкових прогонів кожний | NOT_ACCEPTED_CURRENT_CANDIDATE — Five invariants x1000 not established for this candidate. |
| 4 | Права всіх ролей на всіх API/admin та всіх поверхнях даних | INCOMPLETE — Old fixture failed after an actual HTTP422 but before route sweep; current-environment/access-current-1 has checks=[] and no final receipt. Catalogue195/required95 is static, not all-role execution. |
| 5 | Два одночасні виклики кожної грошової та складської дії | NOT_ACCEPTED_CURRENT_CANDIDATE — Historical concurrency evidence has older source identity; UI same-ID replay and mocked oracles are not all writers concurrently. |
| 6 | Наскрізний процес на чистій базі, звірка до копійки | NOT_ACCEPTED_CURRENT_CANDIDATE — Attempt5 separately accepted transfer/payment UI preview-confirm and same-proposal browser HTTP replay, plus ordinary-document unsupported/no-writes. These3 bounded flows do not establish full business E2E. Exhausted preset not retried. |
| 7 | Backup/restore у чисту установку: кількості, суми, версії, SHA | NOT_RUN_PREREQUISITES_UNPROVEN — Read-only prerequisite review completed at530043a. Usable Linux amd64 runner, compatible offline wheels, pinned Caddy and OpenSSL remain unproven. Same-N restore NOT RUN; no install/upgrade authority inferred. |
| 8 | Чиста виробнича установка: TLS, cookies, proxy, health, logs | NOT_ACCEPTED_BLOCKED_REPEAT — Production install/TLS/cookies/proxy/logs not accepted. A09 exact13MiB retry remains forbidden. |
| 9 | Оновлення N → N+1 та відновлення N після rollback | NOT_ACCEPTED_BLOCKED_REPEAT — A10 activation/upgrade/rollback restriction remains; no new run. |
| 10 | Браузер: 390/768/1440, 200%, клавіатура, Escape, мережа | ACCEPT_SCOPED_EXACT_646D3B8 — Independent root accepted actual attempt5: exit0,7of7 at646d3b80597e087a1ada14221024ec40588996f0/source98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a.26 artifacts hash/length verified. Exact child8084/launcher12712 exited; source/DB unchanged. Attempt4 focus FAIL at530043a preserved. Does not cover PR2 or future merge. |
| 11 | Чиста Windows / Python 3.12: критерії 1–3 і 6 | NOT_ACCEPTED_CURRENT_CANDIDATE — Windows source/stdlib proofs and Python3.12 runtime do not establish fresh Windows criteria1-3 and6. |

Каталог195 definitions /95 required field IDs — static/discovery, не рольова приємка. Skipped CI jobs не PASS застосунку. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`; історичні P05 3/3, A09 exact13MiB, A10 activation/upgrade/rollback та заборонений A11 cloud route не змінюються.

## Прогалини й наступний власник

- Gate10 and persistent demo are accepted exactly at646d3b8/98b011. A future source change or PR2 merge requires evidence reconciliation; the prior530043a attempt4 remains FAIL.
- Access-current-1 is interrupted/incomplete: checks=[]; no final original exit or complete cleanup receipt. Do not resume it from this task.
- Final candidate has no full11-gate acceptance; historical results are attached only to their old source identities.
- Historical mixed-EOL FLOW route/fixture raw source hashes lack relocated exact original bytes; these are explicitly unbound, not assigned to later DOC UI source. Current accepted mixed-EOL sources are normalized only after raw-hash verification.
- S1/FLOW/DOC shared source evolves across commits. Earlier22/8/5 receipts retain original source identities. A separate focus-fix manifest records a new22-case recovery run and4 focus cases at646d3b8; no single combined22+8+5 current run is claimed.
- Several controlled/build logs have no numeric original process exit in their manifest. Raw PASS and recorded review are retained without invented exit0.
- Dedicated hash-scoped verdict files for pure S2/server/FLOW are absent from their local evidence folders; chief-coordinator saved acceptance is linked explicitly.
- S2 is synthetic one-line/full-PO read-only matching; no AI/OCR, persistent exceptions, approval, supplier bill posting, or complete document-to-operation acceptance.
- Restore prerequisite read-only review is complete; usable Linux/wheels/Caddy/OpenSSL are unproven and restore remains NOT RUN. No installation or A10 approval is inferred.
- PG preflight has0 test attempts. Root-reviewed isolated fixture portability correction has2 SQLite validations, not PostgreSQL acceptance; its patch and any new synthetic cluster plan remain outside this four-file handoff.
- Remote publication is only at saved3d979060 snapshot;11 local commits and this registry patch are not declared published. Exact publication ownership remains with the designated integrator.
- Separate PR2 is RECONCILIATION_PENDING: reported head abb8845f6563bafa806029ddc1e7c2cace09907c and product b10760b16dfe933511cd880f02a29d840c03dcc1 are not integrated. Its network/transfers/retentions/datasets features and tests are not attributed to this candidate. Independent comparison belongs to browser_evidence_check.
- Old automatic cleanup refusal remains: C:/Users/user/AppData/Local/Temp/bos-verify-2p4lvh7y must not be retried via another path.

Actual attempt4 exit1/zoom200/focus збережено при530043a. Прийнята attempt5 exit0 і persistent demo прив'язані тільки до646d3b8/98b011. Preview/replay business hashes звірено для transfer/payment, ordinary document нічого не записав. Повні сценарії залишаються відкритими. Restore precheck завершено: Linux/wheels/Caddy/OpenSSL непідтверджені, restore NOT RUN. PG preflight має0 test attempts; окрема fixture portability correction має2SQLitePASS, не PG PASS; її patch сюди не входить.

Патч змінює тільки STATE.json, QUEUE.json і два документи orchestration. Old checkout, active/frozen source, external reservation, remote refs і історичні raw не змінюються. Перевірка застосовності виконується `git apply --check` на окремій копії двох точних base blobs; застосування до active tree не виконано.
