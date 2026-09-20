# Мережа та операції · адресне приймання

Доручення: «делай все этапы», 20.09.2026. Зафіксований runtime цього звіту: `f00a2faf10ebcc4bc120b34f7d15d9bf889fa491`, SHA256 `c15dfe0e3aeefde2fd4fa7af0e9dd2c7c04072a59b185554b821576b4c2111ca`. CI-кандидат: `929a395547fa1ed496171120a14b19bc8d5b6f87`. Ветка: `feat/network-operations-20260920`, PR2.

## Валюта та точка виробництва

NETWORK-PLAN-CURRENCY прийнято незалежним reviewer. 12 адресних регресій відтворили помилку до виправлення та пройшли після нього без зміни assertions. Підбір виробничих робіт, готових партій, матеріалів і закупівель враховує валюту; резерви у несумісній валюті або іншій точці пояснюються замість непридатної наступної дії. Сумісна пропозиція перевірена через чинний writer. Історичні записи не конвертуються. Приховані/непридатні старі резерви можуть вимагати окремої звірки; повна оптимальність планувальника не заявлена.

## Історія виконання CI

| Invocation | Кандидат / run | Фактичний результат |
|---|---|---|
| 1 | `0975280` / 35516152992 | Workflow validation failure, жодного job. Дві змінні runner.temp були в недопустимому job env |
| 2 | `b54b621` / 35516516284 | PG16.15 підключено, worker TypeError до methods; Chrome152 виконав login, але harness пропустив onboarding. Бізнес-перевірки не виконані |
| 3 | `929a395` / 35516896359 | PG2/2 PASS; browser57 assertions до timeout оплати, scope не завершений |

Виправлення CI/harness незалежно перевірені, окремі atomic commits. Первісний YAML/AST review пропустив обмеження GitHub contexts; початковий browser review не врахував onboarding та wrapped SELECT labels. Ці помилки й невдалі artifacts збережені. Результат приймання визначається виконанням, не самим review source.

## Незалежний результат

PG: **ACCEPT_SCOPED_POSTGRES16_TWO_NETWORK_MUTEX_CASES**. PostgreSQL16.15, Python3.12.14, два methods за4.260s, exit0. Два незалежні live lock proofs з holder/waiter/observer, однаковими HTTP200 receipts, одним ефектом та незмінним replay. Джерельна canary й runtime незмінні, видалення виділеної test DB підтверджено.

Browser: **PARTIAL_EVIDENCE_ACCEPTED_FULL_BROWSER_SCOPE_FAILED**. Chrome152.0.7977.82. 57 assertions пройшли до timeout очікування відповіді payment preview. Це не57 незалежних бізнес-сценаріїв. Підтверджено CEO login/onboarding,4 групи,DOM карти/точок, фільтр філії/точки/валюти, CSV, ручний конвертер, окрему EUR історію, документ/Escape/focus, preview/cancel, dispatch→receive→quality та replay, створення утримання без зменшення дебіторки. Отримано4 бізнес-квитанції.

Payment/release/final settlement, mobile390/320 та manager/observer до виконання не дійшли. Причина timeout **не встановлена**: source endpoint правильний, видимі поля валідні, журнали фіксують відповіді й не доводять, чи був запит ще в роботі. Не збільшено timeout і не змінено assertions заради PASS. Ліміт network workflow3/3 вичерпаний; автоматичного повтору немає.

Незалежно переглянуто5 screenshots. Знімки показують верх внутрішньої scroll-pane; карта/реєстр/документи/етапи нижче не потрапили в кадр. KPI на1440 розриває цифри й «грн» між рядками; цей фактичний дефект передано CORE-WORKSPACE-VIEWS. Full visual acceptance не заявлено. Source/data canaries незмінні, synthetic DB/media видалені.

## Збережені докази

`evidence/network-acceptance/final/`: pg-artifact.zip (SHA256 `9fe4efbb026fab2cd72f92219ef25d7d1b26187b2574cd675405d45824734f4f`,6602bytes), browser-artifact.zip (`a2a13199ce4ba86803d9a9daf8854bdf08599bc3bdb03a52519e617c4d9edb42`,936536bytes), окремі reports/reviews і Git runtime verification. Перевірено6PG та14browser indexed artifacts. 366 runtime Git blobs коміту0975280 збігаються з локальними. CI-кандидат929a395 має той самий c15d source digest після виключно CI/evidence змін; прямий Git-tree proof929a395 не заявлено. Whole checkout не заявлено перевіреним. Історичні failures у ci-context/, pg-runner-fix/, browser-onboarding-fix/.

## Межі

Це нові обмежені сценарії мережі, не повний suite або історичний E2E. Ліміти P05, A09/A10/A11, erp.test_network та erp.test_network_integration не скидаються. Windows, фізичні мобільні пристрої, всі 11 GATES, production migration/activation та пілот не прийняті. TECHNICAL_READY=false, PILOT_ALLOWED=false.

Браузерний scope не включає RFQ/quote/purchase creation UI, живу зміну прав під час читання, typed stale recovery, ін’єкцію втрати відповіді confirm, reload конвертера, повну JSON export equivalence чи повний accessibility аудит. Наявні backend/Node докази доводять тільки власний scope. Синтетична історія не оголошується прискоренням реального бізнесу.
