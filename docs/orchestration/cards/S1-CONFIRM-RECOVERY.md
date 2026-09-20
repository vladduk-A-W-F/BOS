# S1-CONFIRM-RECOVERY · 20.09.2026

Статус: implementation complete, independent root review pending. Base: `3d979060fe9862119ba8ad6c9d8bd505103796e3`; runtime code base `e66af863b0bd840cefb4ef78e5a17414411f3db8`.

Причина: звичайний ERPActionDialog втрачав proposal_id після будь-якої помилки confirm. Втрата відповіді після запису могла привести користувача до нового preview замість безпечного повтору збереженої квитанції.

Allowlist: `frontend/boss_app_source.html`; generated `frontend/boss_app_html.html`, `assets/app.js`; новий `scripts/check_confirmation_recovery.cjs`; ця картка. Root володіє backend, STATE, QUEUE, PR та інтеграцією. Центральні models/migrations/policy/service не змінюються.

Результат: до надсилання confirm вкладка зберігає тільки proposal_id/action. Редагування та новий preview тієї ж дії блокуються, доки є незавершене підтвердження. Відновлення доступне у спільному списку ERP, включно після закриття діалогу або reload. Відкриття списку нічого не виконує; повтор надсилає той самий ID до чинного confirm endpoint. Payload, суми, паролі, session/CSRF tokens не зберігаються. Ключ локального списку включає identity/access scope і SHA256 CSRF token лише як UX binding, не як доказ серверної сесії. Серверні identity/Policy/replay залишаються авторитетними.

Generic409 об’єднує stale/expiry та конкурентне виконання; UI зберігає невизначеність і дозволяє тільки той самий повтор. Перший 404/422 з JSON error дозволяє явне виправлення форми; після попередньої невизначеності такий самий статус не доводить відсутності commit. Auth/access change приховує попередні дані. Перевірена квитанція відокремлена від помилки подальшого refresh.

Інтеграція робочих точок: звичайний ERP-діалог розташований поза частиною, яку скидає `bos:data-changed`. До confirm він позначає незавершений запит у батьківській панелі; панель зберігає цей діалог і його дозволені джерела, але прибирає застарілі загальні факти. Після визначеної первісної відмови позначку знімає. Auth/access change завжди закриває діалог і приховує попередні дані. Це потрібно, оскільки чинний global fetch wrapper надсилає подію одразу після успішних HTTP headers, до читання JSON квитанції.

Перевірка: `node scripts/check_confirmation_recovery.cjs` — **22 PASS**; `node scripts/build_frontend.cjs` — PASS; `node scripts/check_frontend.cjs` — PASS. Чотири нові спільні випадки викликають actual `WorkpointsPanel` → `BoSActionDialog` → `ERPActionDialog` та actual global fetch з окремими hook-lifetimes. Вони примусово рендерять батьківський invalidation до завершення delayed JSON body, перевіряють збереження діалогу/відсутність abort, відмови refresh 409/503 зі збереженою квитанцією, сторонню mutation і повтор того самого ID, скасування editable-форми після первісної відмови та auth revocation до пізньої квитанції.

Raw evidence: `work/vertical-ua/scenario1-evidence/behavior-attempt-3.txt`, `build-v2.txt`, `frontend-checker-v2.txt`; попередні attempt-1 з помилкою обходу тестового дерева і attempt-2 з 18 PASS збережені. `S1-CONFIRM-RECOVERY-v2.patch` і `manifest-v2.json` містять точні файли, SHA256 та розміри. Набір моделює server idempotence та React hook lifetimes і не є доказом PostgreSQL/Django/browser/DOM/TCP. Existing backend replay contract прочитано в `operations.service.execute`; нового DB або browser прогону ця картка не виконувала. `FLOW-ORDER-SETTLEMENT` залишається окремим відкритим інкрементом. TECHNICAL_READY/PILOT_ALLOWED не змінюються.

Критерії: lost response → exact-ID retry; повторні transport/5xx/409/invalid receipt; double click; IDs-only reload; auth/revocation; unmount/late response; storage/binding failure before send; Decimal strings; жодного автоматичного confirm/new intent.
