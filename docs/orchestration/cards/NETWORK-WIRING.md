# NETWORK-WIRING · остаточна композиція

Доручення: інтегрувати розділ як робочий функціонал BoS. Автор root; незалежний reviewer integration_diagnosis.

Причина: окремо прийняті network і workflow потребують одного нормалізованого зрізу й перевірки доступу на рівні HTTP. Відсутній currency має однаково означати UAH. Новий `measured_at` не може бути рівним між різними читаннями; regression-test перевіряє монотонність дати й рівність решти payload. Підписи доступу відповідають фактичному enum operational/management/ceo.

Allowlist: erp/network.py, erp/test_network.py (адаптація точного assertion до нового контракту, без послаблення даних/прав), erp/test_network_integration.py, frontend/boss_app_source.html, scripts/checks/network_ui.cjs, generated assets/app.js і frontend/boss_app_html.html, ця картка/evidence.

Критерій: default UAH узгоджений; read-only GET/JSON export; зміна доступу під час workflow дає409; timestamps реально є у models і migrations; UI показує чинні рівні. Два HTTP-тести фінального складу PASS, UI19 PASS, frontend build PASS, migration consistency PASS. Незалежний висновок ACCEPT_SCOPED у evidence/network-operations/final-review.json.

Історія: перший composition invocation зупинився на ImportError після відхиленого patch dry-run (моделі помилково позначено новими файлами); другий PASS до фінальної нормалізації; третій фінальний PASS після неї та перевірки created_at. Більше не повторювати цей модуль автоматично. Повний NETWORK-READ теж не повторювався. Проміжна перевірка міграцій виявила відсутні timestamp-поля в canonical models; повторно накладено точний reviewed delta, фінальний check чистий. Причина проміжного розходження файлів не встановлена; фінальні моделі byte-match reviewed source.

Це не PostgreSQL concurrency або browser acceptance. TECHNICAL_READY=false, PILOT_ALLOWED=false.
