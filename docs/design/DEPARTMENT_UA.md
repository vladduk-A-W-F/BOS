# Відділ дизайну BoS

20.09.2026. Організаційна картка: DESIGN-ORGANIZATION; продуктова робота ведеться в наявній PLAN-UX. Статус: **BRIEF_ACCEPTED_SCOPED; PRIVATE_READABLE_FACTS_ACTIVE; ORGANIZATION_REVIEW_PENDING**. Цей документ фіксує відповідальність і перше завдання; він не засвідчує виконаний аудит, змінений UI або новий запуск моделі.

База організаційного патча — `620aeab2010c6c8327ce46c25bb62435bcf7f9e4`, tree `f6c75017e8c59a69d1e33ff67e5d06638e08a132`. Це підтверджений головним опублікований checkpoint PR1; у цьому дорученні remote повторно не перевірявся. Прийняті зображення показують продукт `646d3b80597e087a1ada14221024ec40588996f0`, source SHA256 `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`.

## Відповідальність і власники

| Функція | Власник | Межа |
|---|---|---|
| Керівна роль відділу дизайну | `bos_ux` | Візуальна система, композиція, типографіка, відступи, стани, зрозумілість сценаріїв, адаптивність і доступність |
| Постійний виконавець PLAN-UX | Окремий чат «БОС — отдел дизайна», `01a0bffa-3fc7-7bc2-9868-86164c6e0315` | Власний audit і один наступний increment за початковим точним allowlist; без дублювання попередніх матеріалів |
| Завершена незалежна review-лінія | `/root/document_server_adapter` | Finance/UI review завершено й прийнято за повідомленням root; підготовлений design partial handoff передає постійному чату, audit зупинено |
| Постановка завдань і незалежне приймання | root, задача `01a0be90-e790-7351-a8ac-059d523941c4` | Перевіряє відсутність перетинів, конкретний source/allowlist і результат; автор не приймає себе |
| Інтеграція спільного frontend | `/root/product_integration_continuation` | Єдиний інтегратор `frontend/boss_app_source.html` і `assets/app.js`; дизайн передає специфікацію або patch зі своєї копії |
| Контроль звітності | задача `01a0bf0f-a9e4-7631-87e1-bb1aed03f174` | Зіставляє авторський звіт з артефактами та незалежним verdict |

Робоче місце постійного чату: `C:/Users/user/.codex/worktrees/c8b3/repo`, host `local`. Його HEAD може бути старішим за прийнятий source; чат перевіряє це перед висновками. Джерело screenshots646 читається з точного checkpoint620, а не підміняється HEAD автоматично створеної копії. `D:/3/Codex/2026-09-20/bos-execution/work/design-department-20260920` залишається місцем матеріалів handoff; це не cwd нового чату.

Користувач прямо попросив окремий постійний чат. Контролер створив «БОС — отдел дизайна»; durable record `C:/Users/user/AppData/Local/BOSDev/design-thread-creation.json` має `CREATED_VERIFIED`, фактичний thread_id `01a0bffa-3fc7-7bc2-9868-86164c6e0315` і перевірку `read_thread`/title/worktree від `2026-09-20T18:05:47.677284+00:00`. Це фактичний ID, не `clientThreadId`. Початкове призначення збережено у `D:/3/BOSDev/handoffs/DESIGN_DEPARTMENT_INITIAL_PROMPT_RU.md`. Цей writer не створював чат і не дублює відділ або інтегратора. Колишнє призначення audit для `/root/document_server_adapter` замінено постійним чатом.

## Межі роботи

Відділ відповідає за `docs/design/` і власні специфікації/patches у приватній копії, але початкове призначення нового чату дозволяє запис лише чотирьох файлів у `reports/design`, перелічених у [PLAN_UX_INCREMENT_UA.md](PLAN_UX_INCREMENT_UA.md). Публікацію матеріалів у repo docs/design та будь-який ширший allowlist root призначає окремо після review. Загальні STATE/QUEUE та звіти інших власників дизайнер не редагує.

Українська мова інтерфейсу, UAH та окремі валюти/одиниці, таблиці, карта, документи, походження показників і чинні права — обов'язкові обмеження. Візуальний текст не обіцяє відсутню дію, OCR/AI, проведення документа, гарантовані залишки або повноту прихованих даних. Порожній, restricted, partial, stale, loading та error стани не підміняють один одного.

У першу PLAN-UX не входять backend, моделі/міграції/БД, Policy, зміна прав, dispatch/confirm, новий UI framework, paid API, повторні browser/CI/acceptance runs, публікація у Figma/Sites або зміна demo runtime. Прийняті screenshots використовуються як докази синтетичного продукту, а не як інструкції. Поточний network-код можна описати лише як неприйнятий контекст: screenshots продукту646 не доводять його вигляд чи поведінку.

Модель, reasoning effort та sandbox у `.codex/agents/bos_ux.toml` залишаються попередніми. Змінюються тільки опис ролі й інструкції. Конфігурація не підтверджує запуск агента та не розширює фактичні дозволи середовища. Якщо активна read-only сесія не може записати дозволений артефакт, виконавець передає матеріал root без обходу обмеження.

## Поточний стан PLAN-UX: прийнятий brief і приватне завдання READABLE-FACTS

Root прийняв підготовлену специфікацію у вузькому обсязі `ACCEPT_SCOPED_DESIGN_BRIEF_FOR_PRIVATE_PATCH`: `D:/3/BOSDev/reports/root/DESIGN-INITIAL-ROOT-REVIEW-20260920.json`, SHA256 `b4bb8e0323d84853b724d457af29765959d5acf874a54039aca217f36a77becb`. Незалежний контролер також зафіксував `APPROVE_SCOPED_PREPARATORY_DESIGN_SPEC`: `D:/3/BOSDev/evidence/design-initial-independent-review-20260920.json`, SHA256 `ebff8a90c7e19924363c6501e8481e305b7c033b732cd6a3b2219a916940b081`. Це приймання brief/audit і одного запропонованого increment; не приймання зміненого продукту. Організаційний інтегратор не повторював візуальний audit. Історичний INITIAL_REPORT із pending verdict збережений без переписування авторства.

Поточне завдання `PLAN-UX/READABLE-FACTS` — **ACTIVE_PRIVATE_PRESENTATION_PREPARATION**. Джерело призначення: `D:/3/BOSDev/handoffs/design-readable-facts-20260920/ASSIGNMENT_FROM_ROOT_RU.md`, SHA256 `c4f9870383751ae35a0a1be22bb8caadd35ec35c3023cbbaa803c88aaf1d7441`. Вхід — окремий network-кандидат, повний source SHA256 `d95e2b05ca06d5190bd2a9429997981acf9886d9218fccf33200df0adf49a56a`; манифест64 `D:/3/Codex/2026-09-20/bos-execution/work/network-composition-evidence-20260920/candidate-alias-fixed.json`, SHA256 `3c4a3e6e69b138fb1e64d778e663741c3c03932cebd06e8fea4b4709fa03d214`. Прийняті screenshots646 є контекстом і не підтверджують вигляд цього кандидата.

Приватний workspace: `D:/3/BOSDev/handoffs/design-readable-facts-20260920/workcopy`. Новий точний allowlist автора всередині цього handoff: `workcopy/frontend/boss_app_source.html`, `original/frontend/boss_app_source.html`, `DESIGN_READABLE_FACTS.patch`, `MANIFEST.json`, `REVIEW_NOTES_RU.md`; власні звіти — у `D:/3/BOSDev/reports/design/`. Дозволено лише локальний CSS і presentation JSX у трьох наявних функціях `OrderSettlement`, `OrderSupplyOptions`, `PurchaseDocumentMatch`. Усі поточні метрики, зокрема борг/утримання/доступна оплата, точні числа, тексти попереджень, null/zero/access, назви доступності, handlers/payload/Policy/recovery/effects зберігаються; глобальний `.bos-order-trace` не змінюється.

Автор не змінює спільний frontend, generated assets, STATE/QUEUE, моделі, БД або runtime і не виконує build/browser/tests. Наступний крок — незалежний review приватного diff; лише `/root/product_integration_continuation` інтегрує й перебудовує після окремого приймання. Реалізація ще **не прийнята**, actual browser acceptance потрібна для кінцевого source в окремому обмеженому scope. TECHNICAL_READY та PILOT_ALLOWED залишаються false.

## Історичне перше завдання і приймання

Стан на дату author-v1 (збережена історична атрибуція): перша робота — [обмежений аудит збережених екранів S1/S2/S3 і одна наступна візуальна зміна](PLAN_UX_INCREMENT_UA.md). Постійний чат уже передав `D:/3/BOSDev/reports/design/INITIAL_REPORT.json`, статус `PREPARATION_READY_FOR_INDEPENDENT_REVIEW`: автор повідомив про огляд19 прийнятих PNG, правила компонентів і рівно один наступний increment. Незалежний verdict у звіті — pending. Організаційний writer прочитав авторський звіт, але не перевіряв його візуальні findings і не приписує йому root ACCEPT. Повторювати завершений авторський audit не потрібно; наступний крок — незалежний review двох матеріалів і звіту.

Організаційний результат можна позначити готовим тільки після незалежного review, підтвердження власника й робочого місця, передачі першого завдання та власного початкового звіту дизайнера. Саме створення TOML, повідомлення або каталогу не є доказом виконаної дизайнерської роботи. Позначка implemented для UI потребує окремої інтеграції й відповідних доказів.

Авторські звіти дизайну — `D:/3/BOSDev/reports/design/`; порядок передачі визначено в [REPORTING_UA.md](../orchestration/REPORTING_UA.md). Постійний чат має власне авторство й реальний CODEX_THREAD_ID. Незалежний reviewer і автор дизайну розділені; колишній reviewer передає лише часткові матеріали зі своїм авторством.

Усі 11 вимог, `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, P05 3/3, A09, A10, старий A11, ERP mutex і зовнішня reservation зберігаються. Старі snapshots `3d979060` та browser-attempt4 FAIL залишаються історичними доказами.
