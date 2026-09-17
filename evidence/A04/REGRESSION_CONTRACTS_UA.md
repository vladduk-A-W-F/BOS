# A04 · незалежні регресії доступу

Джерела: прийнята `ACCESS_AUDIT_UA.md` (розділи 3–5), поточний `docs/PROGRESS_UA.md`, фактичні Django routes/models/serializers/views. Координатор конкретизував позначення Д/Е, document scope та історію чатів перед написанням тестів. Нових бізнес-ролей немає.

Файл: `/workspace/scratch/c7b51e996a9f/tmp/a04_test_access.py`.
43 test methods; сім груп. Тестові fixtures містять EUR, USD і UAH, оплачувані зарплати з реальними витратами, окрему непов’язану salary transaction, видимі/закриті документи та версії, договори, закупівлі, ERP, події й повідомлення.

| Група | Методів | Контракт |
|---|---:|---|
| `A04FinanceReadTests` | 6 | CEO зберігає всі потрібні дані. Manager/observer бачать мінімальний робочий довідник. Зарплати — тільки CEO; observer не отримує transactions; manager отримує погоджений allowlist без salary sources. Реальні `.json` та `.json/` aliases. |
| `A04AggregateReadTests` | 8 | Вкладені ERP/home/events, dashboard, activity, summary, next step та change/order details застосовують ті самі права. Дозволені складські записи й закупівельні ціни manager залишаються доступними. |
| `A04DocumentReadTests` | 9 | Поля/permissions існують; default доступ старих документів — ceo. Scope застосований до списку, версій, snippets, related requests, contract aliases, compare і RFQ. Download окремий, зміни прав діють у поточній сесії. |
| `A04ExportTests` | 4 | Окремий export capability для CEO/manager; observer завжди заборонений. Експорт використовує рольову проєкцію, відкликання працює одразу. |
| `A04ProposalAccessTests` | 4 | Обидва preview adapters блокують CEO-only actions і закриті document IDs. Task proposal не обходить scope через request_code. Confirm повторно перевіряє document capability, зберігаючи відсутність побічних ефектів при відмові. |
| `A04AssistantAccessTests` | 10 | Сценарні відповіді й джерела фільтровані. ORM context вимагає request, повторно читає role/permissions та ігнорує старі глобальні caches. Історія власна і враховує роль з моменту створення. DELETE архівує власні видимі записи, зберігаючи PK/links/bytes. |
| `A04BoundaryReadTests` | 2 | Анонімний клієнт залишається анонімним і не читає жодну поточну бізнесову GET поверхню; HEAD/OPTIONS не видають payroll canaries. |

## Погоджена конкретизація

- `operations.export_workspace`: додатковий Django permission для CEO/manager, observer завжди 403.
- `operations.view_document`: потрібен manager/observer; CEO має право бачити всі documents.
- `operations.download_document`: додатковий permission для будь-якої ролі, також CEO; не розширює object visibility.
- `Document.access_level`: `operational`, `management`, `ceo`; default `ceo` для старих некласифікованих записів. Manager з Д бачить operational/management; observer з Д — тільки operational.
- Manager transaction allowlist: `id`, `date`, `direction`, `category`, `currency`, `contract`, `counterparty`, `branch`, `archived_at`. Не містить `amount`/`description` чи salary sources. `category=salary` виключається навіть без Salary FK.
- `_build_tasks_context(request)`, `_build_employees_context(request)`, `_build_finance_context(request)` повторно застосовують actor policy. Немає доступу без principal. На A04 кеш цих приватних контекстів прибирається.
- `ChatMessage.user`, `visibility_role`, `archived_at`: NULL legacy не видно в API; чужу історію не видно навіть CEO; старі CEO-повідомлення того самого owner приховані після downgrade; DELETE не стирає історію чи файли.

## Червоний стан до реалізації

Очікуються фактичні HTTP витоки в зарплатах, transactions, documents, snapshots, exports, chat history/сценарних відповідях; незаконні previews; глобальне видалення історії; відсутні нові schema поля. Старі context-функції не приймають request, тому ці тести до правки дадуть TypeError, який навмисно не приймається як рішення доступу.

У `make_document` та `message` є лише сумісне створення синтетичного fixture до/після нових міграцій: нові поля передаються, якщо вони існують. Відсутність схеми окремо дає червоний результат. Немає підміни ORM, endpoint-ів чи зміни віддаваних HTTP даних у тестах.

Позитивний CEO контроль реально запущено на окремій SQLite: 1 test, OK. Лог: `/workspace/scratch/c7b51e996a9f/tmp/a04_draft_setup.log`. Повний red запускає координатор. PostgreSQL не запускався. Реальні `db.sqlite3` та `BoS_Demo.sqlite3` не відкривались. Жодних змін checkout цим агентом.

## Межі

Це глибокі перевірки даних, а не заміна route sweep: незалежний `ci_review` готує coverage фактичного resolver, методів і admin. A03 login/identity regressions не дублюються. Синтетичний login використовує справжню сесію і групу, без зайвого Employee, `force_authenticate` чи monkeypatch. MD5 hasher налаштовано лише на цей синтетичний набір для швидкості fixture setup.

Legacy LLM без ключа лишається недоступною; ці тести не видають 503 за доказ працездатної зовнішньої моделі. Приватний ChatFile перевірено через наявну історію й заборону загального `/media/` доступу. Новий маршрут завантаження ChatFile не вигадано.

Старим бізнесовим тестам із законним export/download потрібні явні permission fixtures, оскільки роль CEO сама їх не надає. Їхні бізнесові assertions не слід послаблювати, а новим негативним A04 клієнтам ці capabilities не видаються автоматично.
