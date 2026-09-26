# A03 · передумови справжнього входу в наявних перевірках

11.09.2026. База: A05 commit `212fcf8`, 151 функціональна перевірка +
5 launcher + 82 наявні Django/unittest-тести. Це read-only карта змін;
код checkout прочитано без редагування; реальні SQLite-файли не читались
і не змінювались.

З root узгоджено: групи `ceo`, `manager`, `observer` у нижньому регістрі.
Demo POST `/api/operations/role/` зберігається і входить в іншого справжнього
demo User; у working цей endpoint повертає404. Тому наявні role POST та всі
assertions щодо ролей залишаються. Додаткових Employee для входу немає.

## Контракт допоміжного входу

Один helper, наприклад `login_test_client(client, role='ceo', username=None)`
у вже наявному `scripts/check_support.py`. Helper працює з переданим справжнім
`Client`/`APIClient`, не створює альтернативний транспорт і не обгортає HTTP.

1. Створює нового синтетичного `get_user_model().objects.create_user(...)`.
   За замовчуванням — новий username для кожного окремого клієнта, наприклад
   `bos-test-{role}-{uuid4().hex}`. Звичайний бізнес-користувач не superuser/staff.
2. Виконує `user.groups.set([Group.objects.get_or_create(name=role)[0]])`:
   рівно одна потрібна група. Значення поза трьома прийнятими ролями відхиляє.
   `anonymous` не є роллю helper і не може непомітно перетворитися наCEO.
3. Викликає справжній `client.login(username=..., password=...)`; false —
   негайна помилка передумови. Не використовує force_login, force_authenticate,
   bearer-підстановку, зміну request.user або monkeypatch middleware/ORM/HTTP.
4. Повертає User за потреби; не створює Employee, Branch, фінансових рядків,
   business AuditEvent, не запускає seed і не змінює лічильник `checks`.
5. GET для нового CSRF-cookie виконується вже **після login** у call-site,
   до першого бізнес-запиту. Створення клієнта, його flags і post helpers
   зберігаються. Для існуючих `Client(enforce_csrf_checks=True)` не відключати
   CSRF; для старих `APIClient()` не вводити глобальні обхідні налаштування.

Стандартний `Client.login` виконує authenticate/login та створює реальну
Django-сесію; перевірка власне публічного HTTP login/logout endpoint залишається
у нових A03-тестах. Цей helper не підміняє її.

## Чотири функціональні скрипти: усі 151 assertions лишаються

| Файл · кількість | Точна передумова, яку доповнити | Що лишається без змін |
|---|---|---|
| `scripts/check_original.py` · 32 | Після `migrate` і `c=Client(enforce_csrf_checks=True)` викликати helper; потім існуючий `c.get('/api/operations/status/')`. | Усі route200, create/edit/search, local-only403, AI503, статичні UI/контрастні assertions. |
| `scripts/check_workspace.py` · 22 | Після migrate/трьох seed та створення `c` увійти як normal User групиceo, потім існуючий statusGET. | Повний guided process, суми/залишки/вплив, stale409, role POST observer, read200/write403, SHA assertion. |
| `scripts/check_erp.py` · 49 | Після migrate/seed/repeat seed та створення `c` додати loginceo перед statusGET. | Точні матеріали/витрати/баланси, quarantine, roles observer→manager→ceo через існуючі POST, replay/conflict/assertions без змін. |
| `scripts/check_operations.py` · 48 | У локальній фабриці `client()` після конструктора додати helper і тільки тоді існуючий assert statusGET200. | **Обидва** `c=client()` і `other=client()` отримують різних реальних Users/сесії. Усі count6/8/3/9, audit1, чужий proposal403, CSRF403, role POST, фінансові/документні assertions збережено. |

Чому не cached глобальний `ceo`: `check_operations.py` перевіряє чуже погодження
через `other`. Якщо обидва клієнти отримають одну особу, початкова бізнесова
передумова тесту зміниться. Новий User на кожний client() залишає її точною.

`scripts/check_launcher.py` · 5 — **жодних змін**. Тут немає Django HTTP/DB.
Не підключати auth bootstrap до launcher і не торкатися його поточних assertions.

## Наявні 82 тести: конкретні місця підключення

| Файл / клас або метод | Кількість у файлі | Зміна тільки передумови |
|---|---:|---|
| `tasks/tests.py` · `TaskAPITestCase.setUp` | 7 | Після `self.client=APIClient()` увійти як normal CEO User. |
| `employees/tests.py` · `EmployeeAPITestCase.setUp` | 6 | Те саме; helper не додає Employee, тому create count1, search len1 та A05 archive count1 лишаються точними. |
| `ai_assistant/tests.py` · `ChatHistoryTestCase.setUp` | 2 | Те саме; не створювати ChatMessage/ChatFile або history audit у helper. |
| `finance/tests.py` · `SalaryPayTestCase.setUp` | 5 | Login одразу після APIClient; існуючий Employee зарплатної fixture лишити. Два тести `CounterpartySerializerTestCase` не мають HTTP — їм auth не потрібен. |
| `erp/tests.py` · `FinishIntegrityTests.setUp` | 6 | Login після Client і до statusGET. Існуючого оператора/production fixture не зв’язувати з login User і не змінювати. Auth не вставляти всередину CaptureQueriesContext. |
| `finance/test_payment_integrity.py` · `PaymentIntegrityTests.client_with_csrf` | 6 | Login нового Client перед statusGET. ORM-only виплати не потребують User. У concurrent HTTP тесті всі Users/групи/login створюються послідовно до ThreadPoolExecutor; у worker тільки ті самі бізнес-запити. |
| `finance/test_finance_integrity.py` · `HistoryTestBase.setUp` | 32 | Login нового normal CEO через `self.http` до чинного statusGET200. Одна правка бази охоплює HTTP15/admin9/legacy8 та також 4 успадковані attribution-тести. |
| `finance/test_finance_integrity.py` · `HistoryTestBase.setUpTestData` / `admin_post` | — | Існуючому synthetic superuser додати рівно групуceo. У `admin_post` зберегти справжній існуючий login із його credentials та GETadmin; normal HTTP User й admin User не зливати. |
| `finance/test_archive_regressions.py` · `ArchiveReviewTests.setUp` | 6 | Login існуючого Client до statusGET; **зберегти** enforce_csrf_checks=True і raise_request_exception=False — trigger500/409 перевіряються реально. |
| `finance/test_archive_regressions.py` · `admin_client` | — | Існуючому superuser додати групуceo перед його наявним справжнім login. Не замінювати його force_* методами. |
| `finance/test_attribution_regressions.py` · `AttributionReviewTests` | 4 | Окремої правки не треба: успадковує виправлений `HistoryTestBase.setUp`. Усі синтетичні FK/history fixtures й assertions незмінні. |
| `finance/test_archive_stale.py` · `EmployeeArchiveStaleReviewTests` | 2 | HTTP-клієнта тут немає. ORM serializer тест не змінювати. У direct ModelAdmin тесті existing `request.user=create_superuser(...)` доповнити рівно групоюceo; не перетворювати цей unit-тест на інший HTTP-сценарій. |
| `operations/test_reconciliation.py` · `ReconciliationTests` | 6 | Жодних змін: окремі synthetic sqlite3 fixtures, без Django HTTP/auth. |

Сума файлів таблиці: **82**. Запис «—» не додає тестів, це друга передумова
того самого файлу. Не додавати логін у TestCase глобально: це приховано змінить
нові негативні A03/A04 сценарії та анонімний інваріант.

## Інваріанти: окремі явні фабрики авторизованого й анонімного клієнта

У `scripts/check_invariants.py`:

- `client()` лишається анонімним: не викликати helper/login, не заповнювати
  `_auth_user_id`/group/session role. `contexts={'anonymous': client()}` зберегти.
  Початковий statusGET може бути відхилений; для цих readonly перевірок
  CSRF-cookie не потрібний. Немає підстав авторизувати цей клієнт заради200.
- `role_client(role)` вже створює реальний User і групу. Залишити справжній
  login, зробити групу єдиною через `.groups.set([group])`, виконати statusGET
  **після** login. Видалити тільки ручний запис `session['bos_role']=role`.
  Групи ceo/manager/observer беруться з БД, не з session role.
- Для role_client можна створити `Client(enforce_csrf_checks=True)` прямо,
  щоб він не використовував анонімний statusGET до входу. Анонімна фабрика
  від цього не змінюється.
- Ceo positive control, manager/observer/anonymous запити, paths, forbidden
  fields/markers, кількість ≥1000, усі фінансові/складські assertions та критерій
  відмови401/403 лишаються. Не підміняти response, не розширювати дозволені
  статуси на200 і не прибирати рольовий інваріант.

Сам A03 може закрити анонімну частину, але не повний A04 field-level доступ.
Рольовий інваріант чесно лишається червоним, доки поведінка не відповідає всім
його незмінним assertions.

## Як зафіксувати, що бізнесові перевірки збережено

Зафіксувати A05-baseline `212fcf8` та diff лише наведених setup/factory/import
місць. Окремо порівняти AST усіх наявних `assert`, `self.assert*` і `test(label,
condition)` викликів: зміни їхніх бізнесових виразів або видалення заборонені.
Новий `assert client.login(...)` — додана перевірка передумови, його не включати
в лічильник 151/5. Наявні helper statusGET200 assertions лишаються такими самими.

Після змін список назв старих `test_*` лишається82, у чотирьох скриптах
`passed` лишається22/49/48/32, launcher —5. Нові A03-тести рахуються окремо.
Перевірити seed без додаткових Employee, старий чужий proposal403, явний
CSRF403 та два concurrent HTTP clients — саме ці передумови найпростіше
випадково пошкодити auth-helper зміною.
