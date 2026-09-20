# BoS: пакет доказательств для независимого review

**Статус: DOCS_ONLY_READY_FOR_INDEPENDENT_REVIEW. Техническая готовность и допуск пилота остаются false.**

Подготовлено 2026-09-20T17:33:42.480912+00:00. Единственный текущий интегратор — `/root/product_integration_continuation`, задача главного `01a0be90-e790-7351-a8ac-059d523941c4`. Пакет не возобновляет прерванную реализацию/access sweep и не снимает external reservation.

База: `646d3b80597e087a1ada14221024ec40588996f0`; tree `1b0bf4e03a4e506d76f2d264e173d1bdc23e7fd3`. Frozen runtime `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`. Сохранённый focus-freeze:1988 tracked файлов,1843 различия текстовых CRLF/LF; PDF/остальные bytes exact. Предыдущие commit `530043a80c1196dfcd7bc8bef73b2ec041c09a68`, tree `4f7bb2cfe70cbb95f835e58be5ab1e690e3b8122` и runtime `dae72739e3a4a260d23db5259066636b01258de4093f457537df35292cd892a6` сохранены с исходным freeze и отдельным снимком прежнего пакета. Результаты старых тестов остаются привязаны к своим версиям. Сохранённый PR snapshot от17:00:48UTC показывает опубликованный `3d979060fe9862119ba8ad6c9d8bd505103796e3`;11 локальных коммитов не объявлены опубликованными. Свежей сетевой проверки и публикации в этом поручении нет.

**Координатор независимо принял Gate10 и демостенд именно на646d3b8/98b011.** Actual browser-attempt5: exit0,7/7; отдельно3/3 ограниченных сценария. Все26 артефактов отчёта сверены по SHA256 и размеру. Принятый адрес демостенда: [http://127.0.0.1:8876/](http://127.0.0.1:8876/). Сохранённая квитанция подтверждает обычный CEO login, nonstaff/nonsuperuser, working mode, browser1440/390 без ошибок и оставленный работающим сервер; координатор дополнительно получил publicHTTP200. Я не повторял HTTP/browser и не читал пароль. Инструкция: [LOCAL_REVIEW_RU.md](D:/3/Codex/2026-09-20/bos-execution/work/continuation-evidence-20260920/LOCAL_REVIEW_RU.md); независимое решение: [BoS-browser-demo-acceptance.md](C:/Users/user/Documents/Codex/2026-09-20/realtime-voice-chat/outputs/BoS-browser-demo-acceptance.md). Эти приёмки больше не стоят в очереди как невыполненные.

| Коммит | Карточка | Проверка и границы | Независимый статус |
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

Полная машиночитаемая связь commit→card→source hashes→raw/exit→verdict содержится в [EVIDENCE_INDEX.json](D:/3/BOSDev/handoffs/execution-writer-20260920/EVIDENCE_INDEX.json): 181 файлов доказательств, 115 сверок с заявленными hashes, 68 source bindings. Всего 3 исторических raw-source binding не восстановлены побайтно; они перечислены явно. Текущие Git/frozen hashes есть для каждого source. Это ограничение связи со старым mixed-EOL receipt, не утверждение о новом дефекте.

## Что нельзя считать общим PASS

S3 первоначальный finding отозван: OrderCancellation входит в расширенный MODELS. sqlite-2 сохранил ошибку неверного test assertion; sqlite-3 имеет12PASS. write_revision добавлен как дополнительный барьер. Settlement raw-reference P2 был действительным и исправлен: два relevant теста финальных bytes проходят в mixed7 run с общим exit1 из-за route fixture; затем отдельно проходит исправленный route1. Старые18/18+policy1/1 и промежуточные2PASS имеют свои hashes и не переименованы в новый полный PASS.

FLOW8 controlled cases предшествуют currency correction; её подтверждает отдельный actual-dialog UAH/EUR/USD case. S1 frontend затем расширен FLOW/DOC/focusfix: старый receipt22 cases не переименован в новый. Отдельный focusfix manifest содержит новый recovery22PASS и4focusPASS, exit0. DOC4HTTP+1послеtest-onlyfix и5controlled сохранены отдельно. Discovery9/9 — только discovery; единого22+8+5 прогона нет. Числовой exit не придуман для logs, где его нет в receipt.

Runner12 mock controls и Windows stdlib ownership сами по себе не являются Gate10. Actual browser-attempt4 на530043a сохранена: **exit1, complete=false**, zoom200 PASS, после Escape на390 фокус не вернулся opener; downstream flows не выполнялись. Отдельное исправление WORKPOINT-DIALOG-FOCUS вошло в646d3b8. На этом новом source actual attempt5 завершилась exit0,Gate10 7/7. Preview/confirm для перемещения1шт. и оплаты12.34UAH прошли через UI; повтор того же proposal выполнен HTTP в той же браузерной сессии. Сверено before=after_preview и after_confirm=after_replay по business hashes: дублей нет. Обычный документ вернул unsupported_document без fields/matches/comparison/proposal и без записи. Эти3 scoped flows не закрывают полный Gate6.

Одноразовый browser runtime очищен, child8084 и launcher12712 подтверждённо завершены, source/исходныеDB неизменны. Постоянный демостенд имеет отдельную квитанцию и оставлен работать; проверочные операции из одноразовой базы в него не переносились. Старый access-current-1 имеет checks=[] и остаётся INCOMPLETE. Авторские pending поля старых manifest/final-checkpoint сохранены как исторические; более позднее независимое решение координатора указано отдельно.

Отдельный [PR2](https://github.com/vladduk-A-W-F/BOS/pull/2) — **RECONCILIATION_PENDING**: head `abb8845f6563bafa806029ddc1e7c2cace09907c`, product `b10760b16dfe933511cd880f02a29d840c03dcc1`. Сохранён свежий source-chat read главного; независимое сравнение ведёт browser_evidence_check. Функции network/transfers/retentions/datasets и тесты этой ветки не интегрированы и не зачислены текущему кандидату. В данном поручении сравнение не дублируется, merge отсутствует.

## Все 11 ворот

| № | Неизменённая исходная цель | Статус кандидата |
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

P06 BLOCKED; P05 3/3, A09/A10/A11 сохранены. Skipped CI не PASS. S2 остаётся synthetic one-line/full-PO, read-only; matching не posting, `accept_draft` не утверждает документ. Фактические scoped browser/persisted-state результаты приняты для трёх описанных шагов; все три полных сценария ещё не завершены. Restore precheck завершён, но Linux/wheels/Caddy/OpenSSL не подтверждены, restore NOT RUN. PG preflight сделал0 попыток тестов; отдельная принятая коррекция fixture имеет2SQLitePASS, не PG PASS, и не входит в этот патч.

## Пробелы и последующая интеграция

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

## Патч и проверка применимости

[REGISTRY.patch](D:/3/BOSDev/handoffs/execution-writer-20260920/REGISTRY.patch) изменяет ровно четыре разрешённых пути: `docs/orchestration/STATE.json`, `QUEUE.json`, новые `PARALLEL_SCENARIOS_UA.md` и `CONTINUATION_20260920_UA.md`. В QUEUE сохранены прежние25 IDs и добавлены10 карточек, включая WORKPOINT-DIALOG-FOCUS; существующий UI-LOCAL-RUNNER обновлён в своей строке, всего35. Сохранены исходные11 gates и исторические лимиты. Точные base blobs STATE/QUEUE на646d3b8 сверены с Git; они совпадают с530043a.

`git apply --check` вернул0 на отдельной временной копии точных base blobs в `D:/3/BOSDev/handoffs/execution-writer-20260920/_work/apply-check-646d3b8`. Патч **не применён**; JSON разобраны, зависимости ацикличны. В active/old/frozen деревья, Git refs, CI и БД запись не выполнялась. Приложение, тесты, браузер, установка и restore не запускались. Применение и публикация остаются за назначенным интегратором после независимого review. При новом head/source координатор сопоставляет этот base и новые доказательства.

SHA256 REGISTRY.patch: `1c50318f9f919820c6e5f4c257cce8ad5225d2b117e2b969cba93e9a9627a4fc`.
SHA256 EVIDENCE_INDEX.json: `42c074104269eb6eef429cd2c0457717fb00def07dc9d699280b32d0277814ef`.

Старый auto-review отказ удаления `C:/Users/user/AppData/Local/Temp/bos-verify-2p4lvh7y` («blocked by policy») сохранён как историческое ограничение. Удаление не повторялось; этот путь не является блокером подготовки документов.
