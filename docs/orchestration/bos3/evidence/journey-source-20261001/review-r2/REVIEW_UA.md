# Незалежний review R2: повернення з CRM до навчального сценарію

**Вердикт: ACCEPTED_STATIC_SOURCE_DELTA.** Три findings R1 закрито на рівні зміненого source. Це дає sole integrator точний матеріал для окремого рішення про інтеграцію. Live, browser, visual, behavior, progress і runtime залишаються **NOT_RUN**; product executions=0, readiness=false.

Прийняття контексту записане до предметного review о 2026-09-30 23:24:44 UTC. Review admission SHA-256 `ea93859c43e68d293ea3423a8bf7d3601ab79a9a76208e1e3e1928bf0643a5ff`; snapshot SHA-256 `a28ce0f40209f7a8bff35d6b48c6a328a66afe872b6caf41d014d9e86971409c`; 11/11 посилань snapshot збігаються. Immutable R1 HTML `564df459854f14fc194295343b61246961ba5f2463b1756309645a549a4bcc4b`; R2 HTML `07590f842d31ba7a5935d873b1a1ecd38c37d277ba1578b077d610e8de0aaf9c`; cumulative patch `806a86394aa2e986a5aee7ba259b9b0211b33636189975479ab24ebf84878d5f`. Original CRM R2 seed `fc82733a97c3532cd8ea45ec9dfbfbd96d9274054c83d512b7fa8d40f8772384`; R1 review `b0e60808427b43c82437762386a6e7d619cc7a416a325dce029cf866e42ead9e`.

| Finding R1 | Статичне закриття R2 |
|---|---|
| **JS-01 · P2** — scope після GET | **CLOSED_SOURCE_STATIC.** Після `await` і до `update(state)`/`verified` `loadSession` звіряє живий `bosHttpScope()` із захопленим scope та `returnOrigin.scope`, інвалідовує ticket при drift і очищує session. `loadContent` також не публікує успішну відповідь з іншого scope. [R2:5490–5509](D:/3/BOSDev/evidence/resume-solutions-20260930/main/journey-source-author-r2/frontend/boss_app_source.html:5490). |
| **JS-02 · P2** — error та read retry | **CLOSED_SOURCE_STATIC.** 401/403 і scope drift → `denied`; session 404 або інший case/session → `changed`; network/5xx → `error`. Маскований `runnerCase` не показує попередній успіх. Кнопка «Повторити читання» повторює лише `content/` або `sessions/<case>/` GET; нових start/check/preview/confirm у дельті немає. [R2:5494–5523](D:/3/BOSDev/evidence/resume-solutions-20260930/main/journey-source-author-r2/frontend/boss_app_source.html:5494). |
| **JS-03 · P3** — фокус після повернення | **CLOSED_SOURCE_STATIC.** `returnToTraining` ставить pending focus; ефект після nav=info фокусує наявний `#bos-workspace[data-bos-main]` (`tabIndex=-1`) лише за збігу scope, slug і `bosCanView('info',null)`. При іншому розділі, крім проміжного CRM, pending очищується. [R2:5591–5593](D:/3/BOSDev/evidence/resume-solutions-20260930/main/journey-source-author-r2/frontend/boss_app_source.html:5591), [R2:5749–5756](D:/3/BOSDev/evidence/resume-solutions-20260930/main/journey-source-author-r2/frontend/boss_app_source.html:5749), [main:5810](D:/3/BOSDev/evidence/resume-solutions-20260930/main/journey-source-author-r2/frontend/boss_app_source.html:5810). |

**Нових regression findings у зміненій ділянці: 0.** Це статичний висновок за точним R1→R2 diff. Повторний GET інвалідовує попередній ticket; після unmount cleanup інкрементує обидва read tickets, тому пізня відповідь не проходить guard. При поверненні origin зберігає `case_id`, `slug`, серверний session UUID і scope; перед показом після GET вони звіряються з поточним URL, selected case та session. Натискання «Повторити читання» не очищує origin і не викликає командний шлях. Реальну черговість мережевих подій, фокус і права у браузері не перевіряли.

| Definition of done | Disposition |
|---|---|
| **D1** | Прийнятий в R1 brochure block побайтово збережено (23 785 символів); повторного full review немає. |
| **D2** | Origin handoff `openTrainingCRM` між R1/R2 побайтово збережено (574 символи); session/context boundary перевірено лише в зміненому return path. |
| **D3** | R2 source виправлено JS-01/JS-02; live identity NOT_RUN. |
| **D4** | R2 return guards закрито статично; CRMProposal (1 445 символів) і CRM detail guard block (3 157 символів) побайтово збігаються seed→R1→R2. Live NOT_RUN. |
| **D5** | Error/retry/focus закриті статично; keyboard, visual і behavior NOT_RUN. |
| **D6** | Exact author/review/source/patch evidence та статичні перевірки збережені. |
| **D7** | Незалежний R2 source review завершено; застосування до canonical, delivery та product acceptance лишаються рішеннями sole integrator. |

Перевірки: `Get-FileHash -Algorithm SHA256` підтвердив 11/11 snapshot refs; immutable R1, seed, R2 і scratch/result збіглися з pins. `git diff --no-index --no-ext-diff --no-textconv -- R1 scratch` дав exit **1** (дельта є), а raw stdout **25 232 символи** точно дорівнює `RESULT_MANIFEST.json correction_r2.result.targeted_r1_r2.raw_stdout`. Targeted hunks починаються біля R1 5479, 5498, 5566 і 5729; `--unified=0` показав 32 додані й 8 вилучених рядків у зміненому read/focus path. `git diff --no-index --check --no-ext-diff --no-textconv` дав exit **1** через відмінності, stdout/stderr порожні; whitespace-діагностик немає. Cumulative seed→R2 patch збігається з independently regenerated diff **після нормалізації CRLF/LF**: patch зберігає 12 CR, які PowerShell text capture пропускає. Read-only registry `1bce859370537437c157893065af499c9edd0fefea90b30c2f3384b2b04b1390` і CSS `30e1db301539b97080705c463c0fec14ae6370de577f824318484c42d159fd54` не змінилися.

У дельті нові `trainingFetch` виклики адресують тільки `content/` і `sessions/`; доданих endpoint-викликів `start/check/preview/confirm` немає. Старі бізнес-команди залишаються в коді поза шляхом retry. Немає підтвердженої runtime-поведінки, інтеграції, commit/push або дозволу на нові виконання. Прийняті historical caps, permissions і CRM R2 boundary збережені.

Повний машинний ledger pins, checks і closure map — [REVIEW.json](D:/3/BOSDev/evidence/resume-solutions-20260930/integrator/journey-source-review-r2/REVIEW.json). Його SHA-256 повідомляється після фінального запису; SHA цього Markdown вбудований у JSON.
