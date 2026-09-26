# C01: незалежна вузька звірка UI та API

Початкова frozen UI: `af366b56874ad0adadf7a24e3a09a022f75d9f6c11367641f510dd9fcd6cb3c2`, `tmp/c01_ui_candidate/UI_CANDIDATE_MANIFEST.json`. Прочитано фактичні helper/dialog/history/recovery у frontend, актуальні tasks.commands/history/queries/models, operations execute/projections і access revision. SHA прочитаних backend inputs: REVIEW_INPUT_HASHES.json. Це source/wire review; жодного browser, БД, HTTP або full gate запуску в цьому підетапі немає.

## U1 · явно відмовлений source залишається на екрані

У recover/prepare/commit гілки HTTP403/404 не викликають denyScope. Картка поточного Task, уже прочитана history, доступні orders та ready не скидаються. refreshRecord/loadHistory уже очищують ті самі дані, тому поведінка непослідовна.

Конкретний сценарій: manager відкриває Task або pending update, поки джерельний Document доступний; access_level документа змінюють на закритий; наступний proposal status/preview/confirm повертає404. Policy.access_revision містить user/employee/role/permissions і не залежить від рівня доступу Document. Отже глобальний session-ended тут не очищує UI, а старі факти залишаються видимими після відмови джерела.

Actual extracted source closures виконано з контрольованими403/404 відповідями: **0/6**, DENIAL_RED.json. Це доводить пропущені setters у реальних handlers, але не є browser/HTTP acceptance. Перевірено, що запит викликано до правильного actual wire маршруту. Мінімальна правка — denyScope для403/404 у всіх3 handlers; у recover також скинути застарілий outcome/same_session. Pending UUID/receipt не видаляти, новий proposal не створювати. Root і a11 повідомлені.

## U2 · reopen/result guard розходиться з уточненим backend

Backend дозволяє done→active/process з omitted result або explicit literal result, тотожним поточному. Змінений result при reopen відхиляється: чернетку можна змінити окремим погодженням. UI helper наразі застосовує completion/correction min3 до будь-якого resultpresent, якщо попередній статус done. Це неправильно блокує explicit same short legacy string під час reopen та допускає локальний preview зі зміненим достатньо довгим результатом, який сервер потім відхилить.

Мінімально: визначити resultingStatus=p.status??task.status; strict correction min3 лише за resultingStatusdone; reopen+different literal відхилити з поясненням окремого погодження. Omitted result лишається omitted, статус не примушує створювати новий результат. Семантику надіслано a11.

## Зіставлення без інших знайдених блокерів у межах scope

- UUID audit_id/proposal_id відповідають UUID4 canonical wire; positive Task integer ID перевіряється окремо.
- Pending зберігає лише4 identifier fields, до confirm; generic409/network/5xx не очищують намір. Остаточні locked409 stale/expired відрізняються від read-only expired GET.
- Recovery звіряє proposal_id/action, receipt task_id/audit_id/impact; нова сесія read-only, same_session=false не допускає виконання старого proposal.
- Role/access revision зміна викликає глобальне закриття workspace; IDs у namespace user/role не перезаписуються текстовими джерелами.
- Нова completion потребує явно введеного result і FK; metadata edit legacy NULL не backfill; archive/restore payload не включає status/result.
- History використовує actual scoped endpoint, actual cursor і server diff, не створює довільний diff з legacy payload.

Дочекаємося source fix; узгодження не оголошено завершеним на початковому SHA через U1/U2. Canonical/UI/backend цим агентом не редагувалися.


## Закриття після адресних правок автора

Новий frozen source: `fd283ac01fd50fd2478a5902e492fbed5f16da943ac3731a01b4903a96dec801`.

- U1: той самий незалежний runner повторно виконав лише6 відомих403/404 cases — **6/6**, `DENIAL_GREEN.json`. Current Task/history/orders/ready очищуються; pending не видаляється. У recover outcome скидається в NULL.
- U2: незалежно виконано6 actual helper scenarios — **6/6**, `REOPEN_FINAL.json`: active/process reopen з explicit same short legacy string та NULL FK проходить; змінений literal відхиляється; strict new completion і done result correction зберігають вимоги result/FK.

У межах цієї вузької source/wire перевірки обидва конкретні зауваження закриті, нових блокерів не виявлено. Це не прийняття browser/full gate/backend tests. Frozen UI, backend і canonical не редагувалися цим агентом.
