# C01 · доручення, історія й архів: UI-кандидат

Готовий до незалежного source review та інтеграції root. Релізні файли лише `frontend/boss_app_source.html`, `frontend/boss_app_html.html`, `assets/app.js`; canonical reviewer не змінював. Source SHA `fd283ac01fd50fd2478a5902e492fbed5f16da943ac3731a01b4903a96dec801`, compiled SHA `b8f3f00701e52d4be433a17a9cd27bee934d15ae980afff977ebb4566a3825f0`. Точні base/final hashes у UI_CANDIDATE_MANIFEST.json.

Усі п’ять старих writers у Tasks та окремий Topbar POST замінено входами до одного ControlledTask. Procurement і Assistant користуються тією самою формою. Strict JSON приймає лише create_task/update_task, typed Employee/Order IDs, строки/priority/result/reason; повторні/невідомі поля відхиляються. Старе assignee не переписується, nullable legacy поля не заповнюються мовчки.

Форма має серверний попередній перегляд і фактичний receipt. Нове завершення потребує явного результату та FK відповідального. Reopen лишає попередній результат. Archive/restore — окремі погодження лише з reason/archived, статус і результат не підміняються. Пошук, статусні фільтри та сортування збережено; додано архів з історією/відновленням та read-only режим тієї самої сторінки.

До confirm збережено тільки proposal_id/action/task_id/user_id у поточній вкладці. Storage failure блокує відправлення. Generic409, timeout та 5xx зберігають той самий ID. GET expired/pending/unknown не створює нового наміру. Лише receipt або definitive locked proposal_stale/proposal_expired завершують pending; нова session читає статус, але не виконує старий proposal. Історія отримується з task-scoped cursor API; FK diff objects показано як ID+перевірене ім’я/code.

Кнопки: «+ Нове доручення», «Редагувати», «Архівувати», «Відновити», «Історія», «Переглянути зміни», «Погодити й виконати», «Перевірити результат», «Повторити те саме погодження», «Прочитати поточне доручення», «Прочитати історію», «Попередні події». Робочі вкладки: «Робочі доручення», «Архів».

Перевірено 24/24 meaningful checks у UI_PROOF.json: фактичні витягнуті JS helpers/command closures з контрольованим transport/storage, loss/replay/terminal/concurrency/Escape, typed fields та незмінність захищених ERP/B02/B03 блоків. BASELINE_RED.json містить початковий red: old commit втрачав proposal, Tasks/Topbar raw writers, status overwrite. Ранній runner мав пропущену змінну busy; цей harness error збережено окремо, він не є дефектом продукту. Babel повторно компілюється в пам’яті й точно збігається з app.js.

Додаткові 8/8 відомі review перевірки у REVIEW_GREEN.json підтверджують field-aware буквальний текст, свіжі дані замовлення і приховування current/source/history після explicit403/404 зі збереженим receipt-state. Початковий REVIEW_RED.json збережено. Прийняте root уточнення дозволяє короткий/пробільний result draft для active/process; done/completion/result-correction лишають strict≥3+FK, null не дозволено. Це уточнення контракту, а не ретроспективне оголошення початкового читання дефектом.

Остаточний wire review: 6/6 DENIAL_GREEN перевіряють prepare/commit/recover403/404 з очищенням current/source panels, збереженням pending identity та скиданням stale same_session у recover. 2/2 REOPEN_GREEN підтверджують: одночасний reopen зі зміненим буквальним result потребує окремого погодження; explicit той самий короткий legacy result допускається без нової completion. Попередні freezes та red докази збережені у review_freeze_1/2, DENIAL_RED та REOPEN_RED.

Це не actual browser, не HTTP backend acceptance і не повний gate. Вигляд390/768/1440, zoom200%, реальний keyboard/Escape, реальна мережа й інтеграція ще потребують окремого приймання. A11 не повторювали. Root окремо перевіряє backend/схему/restore/fullverify. Додаткових plugins/dependencies/network permissions немає.
