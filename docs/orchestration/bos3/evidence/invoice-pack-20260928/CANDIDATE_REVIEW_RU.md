# BoS dev.8: независимый review candidate passport

Дата: 2026-09-28

## Scope

Проверены только frozen `INVOICE_DEV8_CANDIDATE.json` и `INVOICE_DEV8_PACKAGING_NOTE_RU.md` относительно product commit `411e222c4687b6a029c027518d3f20453c5849db`, tree `de9357bf9f0555503f1ab58da360ae79629e092f` и installed runtime baseline `d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`.

Ни source/app, ни тесты, build, PDF render, browser, runtime или delivery не запускались.

## Подтверждённые факты

- Candidate JSON SHA-256 `9286497D1AA88177FCA6580B1DDCFABCD7345DE9BB6EAC19B4C7F170D3BACBB2`, packaging note SHA-256 `77632A4782905E0AD57659BFF1247D2D2892A498A4F5892264AE63906619108F`; они согласованы по product/tree/baseline и future passport path.
- Relative to d8, точный non-orchestration delta содержит ровно пять путей: `README.md`, `README_UA.md`, `boss_project/version.py`, `erp/experience.py`, `erp/test_home_projection.py`. Прочие изменения находятся в orchestration/evidence и не названы runtime behavior.
- Все пять delta artifacts и три retained dev.7 references пересчитаны как SHA-256 exact Git blob byte streams из `411e222`; все заявленные SHA-256 совпали. Tree pin также совпал с `de9357bf9f0555503f1ab58da360ae79629e092f`.
- Passport честно отделяет scoped QA: run1, attempt `1/3`, native exit `0` с pins `906`/`9f7` и exact `experience`/test module/harness. Proved ограничен invoice-only USD totals и empty-snapshot EUR fallback; DB, payments, HTTP/browser, policy/endpoints, runtime, lessons/progress и overall readiness явно не proved.
- `assets/app.js`, PDF и PDF manifest приведены только как unchanged dev.7 references. Passport прямо фиксирует отсутствие frontend generation, PDF generation/render и browser QA rerun; они не превращены в dev.8 acceptance.
- Self-hash отсутствует. Future delivery не угадывается: обозначен только `PENDING_SEPARATE_REVIEWED_MAINTENANCE_BINDING`. `TECHNICAL_READY`, `PILOT_ALLOWED`, `MVP` остаются false.

## Verdict

`ACCEPT_SCOPED_DEV8_CANDIDATE_EVIDENCE_PACKAGING`.

Допустим следующий шаг root: интегрировать immutable passport/documentary records, затем выполнить отдельный exact manifest и delivery preparation review. Это не разрешение на delivery и не полный release/readiness verdict.
