# NETWORK-CONTINUATION · виконати решту етапів

Авторизація власника 20.09.2026: «делай все этапы», після створення завдання NETWORK-ACCEPT-PC і NETWORK-PLAN-CURRENCY. Продовжити автономно на доступних дозволених стендах. Код: feature e97382620fc4604c582ef8e4f2ec4cfd3ffa8f5f; runtime b10760b16dfe933511cd880f02a29d840c03dcc1. Setup branch просунувся до8fec775 лише додаванням CI source-bundle, application runtime не змінений.

Послідовність:
1. NETWORK-PLAN-CURRENCY: діагноз production-material підказок; регресія, виправлення, незалежний review. Allowlist erp/experience.py, erp/test_network_currency.py, card/evidence.
2. NETWORK-ACCEPT-PG: рівно два нові concurrency сценарії мережі на реальному PG16; HTTP, real mutex wait і одноразовий ефект. Allowlist .github/ci/network_pg*.py, окремий guarded CI workflow, card/evidence. Не запускати старі exhausted modules/suites.
3. NETWORK-ACCEPT-BROWSER: новий GitHub hosted stand з наявним Chrome, ізольовані synthetic БД/media та реальна auth. Чотири групи, фільтри, доступ, конвертер, конкретні нові network transitions, desktop/mobile. Allowlist .github/ci/network_browser*, той самий guarded CI workflow, card/evidence. Без локальних повторів заблокованих A11/CDN/loopback маршрутів, без browser install fallback.
4. NETWORK-ACCEPT-REPORT: незалежний review точних CI artifacts, SHA/canaries, виправлення підтверджених дефектів у межах картки; оновлення PR2, STATE/PLAN/QUEUE, завдання Codex.

Кожний підетап має окремий atomic commit без amend. Не більше4 активних субагентів. Root єдиний редактор canonical. Чужі/нові remote файли зберігаються через base_tree. Повні NETWORK-READ та NETWORK-WIRING HTTP modules уже мали3invocations; не повторювати й не скидати ліміт середовищем/назвою.

Новий CI запускається лише з reviewed кандидата, заданої гілки та першої спроби. Кількість/обсяг обмежені, немає automatic rerun. Секрети й real customer data не використовувати. Не змінювати main/production/85/12/11GATES/readiness. Якщо стенд не дає доступу, зафіксувати фактичний блокер і завершити незалежні дозволені частини; не приписувати PASS.
