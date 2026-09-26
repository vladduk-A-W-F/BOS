# Мережа та операції · звіт інтеграції

Статус: **ACCEPT_SCOPED_NO_PG_OR_BROWSER**. Runtime candidate `b10760b16dfe933511cd880f02a29d840c03dcc1`; source SHA256 `c1c4de5ab3d783980bc4bbdb114c0b40ea4d06a3c32524fadf84b9411d36200c`.

Код інтегровано у чинний Django/React BoS. Він читає й змінює звичайні ERP-записи через Policy, preview/confirm та mutex. Django production не розгорнуто; main і чинний Sites не змінені. TECHNICAL_READY=false, PILOT_ALLOWED=false.

## Зміни

- Розділ **«Мережа та операції»**: огляд, операції, документи й звірки, контроль строків. Локальна карта України, координати точок/центрів філій, однакові server-side фільтри й таблиці.
- Явні точки закупівель та виконання продажів; країна походження/призначення. Міжнародні процеси мають позначення import/export, без митної інтеграції.
- Переміщення: dispatch зменшує джерело; receive створює окрему pending-партію; допуск якості окремий. Вартість у дорозі належить точці-відправнику.
- Договірні утримання: retained лишається дебіторкою, collectible обмежує manual/statement оплату. Звільнення утримання саме собою не є оплатою.
- Документи згруповані за доступними зв’язками; тип визначений цими зв’язками. Реальні рівні operational/management/ceo. Фільтр філії не є branch ACL.
- Заявка → пропозиції → закупівлі → часткове/повне приймання. Нові creationtimestamps; історичні NULL без вигаданого backfill. Два вікна по 28 днів, щонайменше 3 завершення у кожному; synthetic порівняння вимкнене.
- Нові defaults UAH, усі три нові набори UAH. Історичні валюти збережені. EUR/USD конвертер опційний, ручний, довідковий. CSV/JSON експортують доступний зріз.

## Наповнення

Три окремі профілі: workday, disruption, collections. Кожний створюється лише у власній порожній demo-БД: 7 філій / 14 точок, 13 заявок, 12 пропозицій, 11 пов’язаних закупівель, 33 продажі, 21 рахунок, 14 часткових оплат, 7 утримань, 7 переміщень, 2 виробничі роботи, 28 приватних документів. Партії 84/83/84; disruption має 10 відкритих прострочених закупівель. Повтор не стирає подальші операції. Без акаунтів/паролів або real data.

Інструкції й сценарії: [NETWORK_DEMO_UA.md](../NETWORK_DEMO_UA.md), [NETWORK_FLOW_METRICS_UA.md](../NETWORK_FLOW_METRICS_UA.md).

## Докази та межі

| Scope | Підтвердження | Межа |
|---|---|---|
| Domain | 10 авторських HTTP тестів; 4 незалежні adversarial | SQLite; фінальні timestamps додані пізніше |
| Initial seed | 6 авторських +2 незалежні | Перед розширенням RFQ; історичний доказ |
| Network read | 10 авторських; 2 незалежні RED→GREEN | До композиції workflow; повний модуль не повторювався |
| Workflow + RFQ seed | 6 workflow, 6 seed, 1 додатковий seed-flow; 1 незалежний RED→GREEN | Вузькі synthetic перевірки; не весь suite |
| Final composition | 2/2 HTTP PASS, 0.410s | Єдиний зріз, експорт, race доступу, наявність timestamps |
| UI | 19 checks PASS; 3 незалежні confirmation cases; build PASS | Контрольовані Node/React handlers; не браузер |
| Migrations | Final check: No changes detected | Не production migration/rollback acceptance |

Усі reviews прийняті у своєму scope; фінальний [review](evidence/network-operations/final-review.json) перевірив склад і raw outputs. [Індекс](evidence/network-operations/index.json) містить SHA/байти первісних receipts, фінального review та перевірок складу, зберігає відмови й попередні результати. Шляхи execution у вихідних reports є історичними; index зіставляє їх із локальними файлами evidence.

Виправлено знайдені reviewer дефекти: null замість порожнього address; виконані продажі у простроченій роботі; EUR stock у UAH плануванні; зміна document scope під час read; некоректні navigation targets; суперечливий час quote>PO; різний defaultcurrency network/workflow. Фінальне складання також виправило підписи enum та підтвердило узгоджені timestamp-моделі.

Не приховано невдалі спроби: дефекти HTTP harness у новому read-тесті; ImportError до копіювання workflow; проміжне розходження моделей/міграцій. Причина останнього файлового розходження не встановлена, фінальні моделі byte-match reviewed author source. Ліміт read-модуля3 invocations вичерпаний; composition теж3 invocations включно з ImportError. Не повторювати автоматично. Test assertion експорту адаптовано до нового measured_at зі збереженням рівності всіх стабільних даних; повний модуль після цього не запускали.

PostgreSQL concurrency цього runtime, реальний browser/mobile, production migration/activation та повний acceptance **не підтверджені**. Попередні PG/Windows/Sites proofs належать попереднім candidates. Виявлена давня production-material currency підказка виділена наступною карткою.

## Коміти

| Картка | Commit |
|---|---|
| NETWORK-DOMAIN | `5130ead2501cf73d5ff4201b0cfe827d48faaa2d` |
| NETWORK-DEMO | `61d748909d0e3d960a879df359623d10cbfd60a4` |
| NETWORK-READ | `acda3f1f657d816bacc34592c6eaaa1d7ab3e3fb` |
| NETWORK-UI | `f1132f2eca201adcf0480f459408c982575c1d06` |
| NETWORK-WORKFLOW | `879c4631dba66d8000077e6cf8081dca3f104c33` |
| NETWORK-WIRING | `b10760b16dfe933511cd880f02a29d840c03dcc1` |

Первісний inspected runtime 87b679888c18ed1920f4735aa945dacad514bcaa. Публікаційна база edd5227e666442d8324044559b6e8cf10eaf8be1 містить три нові CI/control commits без application змін; свіжі STATE/QUEUE збережені та доповнені. Remote base_tree зберігає файли, яких немає в локальному snapshot; whole local Git tree не заявлено перевіреним.

## Наступне завдання

[CODEX_NETWORK_TASK_UA.md](../CODEX_NETWORK_TASK_UA.md): конкретне приймання на ПК, адресна PostgreSQL concurrency за доступності нового дозволеного середовища, browser/mobile та окрема NETWORK-PLAN-CURRENCY. Завдання створене; локальний процес Codex на ПК не запущений із цієї сесії. Щоденна перевірка бачить лише синхронізовані GitHub artifacts.


Git runtime identity: усі 365 локальних runtime-файлів збігаються з точними Git blobs фінального product commit; remote runtime має ті самі 365 шляхів. Whole local Git tree не заявлено перевіреним. Evidence: git-runtime-verification.json.
