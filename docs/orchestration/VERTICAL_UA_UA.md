# Українські робочі точки й перший керівник · 20.09.2026

У чинному Django ERP реалізовано зв’язаний інкремент: філія → замовлення → чинні preview/confirm → складські рухи → рахунки/оплати UAH → доступні джерела й документи. Кодова вершина `e66af863b0bd840cefb4ef78e5a17414411f3db8`, runtime SHA256 `7ea639f89ed86ac0bc9fc5ecf201d4d4752fab22e5876700f16a1634e59ffad6`. PR лишається draft до початкової fix-гілки; main не змінювався.

## Продуктові зміни

- `Location` і `SalesOrder` мають необов’язковий PROTECT-зв’язок із філією. Старі записи й валюти збережено. Команди створення використовують той самий service, preview, confirm, mutex і replay; нових write action IDs немає.
- GET `/api/erp/workpoints/` повертає лише доступні Policy джерела. Замовлення належить записаній філії, запас — фізичному місцю партії; міжфілійне виконання не підмінюється одним виміром. Кількості окремі за номенклатурою/одиницею, гроші окремі за валютою, Decimal строки. Суми рахунків враховують активні кредити, reversal та переплату. Це не залишок банківських коштів.
- Non-CEO отримує money=null, available=null і тільки видимі резерви; приховані IDs/суми/кількість не розкриваються. Довідник філій лишається загальним у межах установки; нової branch/tenant authorization моделі не заявлено. Останні300 рухів обмежені глобально й підписані як неповний журнал.
- Реальний BoSHome містить вибір точки, схему координат і групи замовлень, складу, рахунків, документів. Посилання відкривають чинні inspector/trace/actions. Перед відкриттям звіряються workpoints→snapshot→workpoints та access revision; це optimistic перевірка, не атомарний snapshot. Після помилки/відкликання/зміни попередні факти очищаються.
- Нові форми починають з UAH, явна валюта наявного preset зберігається. Немає FX-конвертації або вигаданого курсу. HTTP telemetry вимірює останні20 запитів поточної браузерної сесії до response headers; не зберігає URL/ID/body й не оголошує прискорення бізнес-процесу.
- `seed_bos_ua` додає три синтетичні філії/склади/замовлення: Київ, Львів, Дніпро. Київ має реальні service-події закупівлі, приймання, резерву, відвантаження, рахунку3600.00UAH і оплати1200.00UAH. Львів готовий до відвантаження; Дніпро демонструє пропозицію й заблоковану партію. Старі EUR/USD не конвертуються. Повтор — no-op, prefix collision/working mode відмовляють, збій відкочує весь seed. Локальний demo launcher викликає новий seed після трьох старих.
- `bootstrap_bos_owner` створює першого CEO тільки в порожній working установці. Пароль прихований або stdin, warning echo fallback відмовляє; роль/права/аудит/marker атомарні. Staff/superuser не надаються. Інструкція: [FIRST_OWNER_UA.md](../FIRST_OWNER_UA.md).

## Фіксація і незалежний review

| Картка | Коміт | Review |
|---|---|---|
| FRONTEND-GLOBALS | `b54a736fa89cf062c024c8e1defdf3ec289a8e9c` | time_probe_review, ACCEPTED_SCOPED |
| BOOTSTRAP-OWNER | `90dc8a52eb94efbade07bfd7f64c7aa88779a38c` | ua_vertical_ui_audit, ACCEPT_SCOPED після getpass fix |
| VERTICAL-UA-DATA | `f44a5f59fdf47f57662fddecbabb374f9f9eaed4` | time_probe_review, ACCEPTED_SCOPED після seed/route fixes |
| VERTICAL-UA-UI | `e66af863b0bd840cefb4ef78e5a17414411f3db8` | root незалежно від автора; bracket-read fix та actual API contracts |

Ізольовані копії авторів, root єдиний canonical writer. Усі чотири коміти лінійні, без amend/force/merge. CLI GitHub credentials були відсутні; файли записані чинним connector. Кожен remote blob/tree SHA звірений із локальним Git index; API-created commit встановлено локально лише після точного збігу Git object SHA. `git fsck --full` PASS.

## Докази

[SHA-індекс36 файлів](evidence/vertical-ua/20260920/index.json) містить raw, receipts, actual API fixtures та скрипти відтворення. Індекс не містить БД, PG пароля, runtime ZIP/installer або browser profile.

| Перевірка | Результат і межа |
|---|---|
| Backend SQLite | 15/15,4.157s; до розширення11/11. Початковий SyntaxError нового тесту збережений, до запуску БД |
| Backend PostgreSQL16.15 | 15/15,10.033s tests/41.891s process;11 source hashes unchanged |
| Перший CEO SQLite | Початкові16/16,5.998s; окремий новий warning regression1/1,0.197s |
| Перший CEO PostgreSQL16.15 | 17/17,25.951s tests/52.578s wrapper; дві справжні sessions, один created/один refused |
| UI | 20 controlled actual-JSX cases +3 справжні Django JSON контракти ролей; без browser/DOM claim |
| Build/static | native build/syntax, lexical references, diff-check PASS; migration drift absent |
| Каталог доступу | 192/192 definitions;191 старий збережено.86 required field tests=75старих+11нових. Це ще не повний Gate4 sweep |
| Handler smoke | `/`, `/assets/app.js`, `/api/runtime/status/`200 на новій synthetic SQLite; не TCP/browser smoke |

PG data raw SHA256 `e4a01a496a2f217f3416d4d833eb67c2193351dbe172f82d4dec8144c585fc38`; owner raw SHA256 `65d8ab9c550cef9ebfe6044464758eb4f65b42be62febd37c19477fc363dccd6`. Автор і reviewer звірили raw; головний координатор додатково звірив14 source files. Для OWNER Windows checkout має CRLF; точні Git LF blobs відповідають усім трьом PG receipt hashes. Повтор тестів через line endings не проводився.

Виділені БД кожної картки очищено, відсутність точних двох імен перевірено. У DATA receipt збережено `database_inventory_restored=false`: паралельна OWNER-картка створювала/видаляла свої БД на тому самому disposable cluster. Початкові глобальні списки не були збережені; загальне відновлення inventory не доведено й не підміняється PASS.

## Повний Git і середовище

Джерельний bundle із workflow commit`8fec775319c0311adf09fc83433cd795dbc14425`, run35515479604, artifact10606747322 імпортовано в нову папку `D:/3/Codex/2026-09-20/bos-execution/work/bos-fullgit-20260920`. На імпорті49commits,1892tracked files,9origin refs, non-shallow, точні HEAD/tree, clean/fsckPASS. SHA bundle`8377d49af1d41cd34e4e2e02bf39142ba0913b6279f1f66ae7df7c3c60b99fcd`; ZIP`e43057b6c655a5b1a2f56eeaf9f536fb1ec7b04496141787dc16653a05a605e1`. Старі targeted jobs на цьому коміті SKIPPED, source workflow не запускав app/DB/tests.

Python3.12.14/requirements-ci у новому D:venv; локальний PG16.15 на127.0.0.1:55439, SCRAM, окрема CREATEDB роль без superuser, без Windows service. Бінарні файли походять з офіційного EDB HTTPS ZIP16.15-1; vendor hash/підпис ZIP не встановлено. Окремий EDB installer має Valid Authenticode, але не виконувався й тотожність його payload ZIP не заявляється. Інший infrastructure owner має окремий runtime16.15-4/cluster55432, файли не змішувалися.

## Чинні межі й наступне виконання

TECHNICAL_READY=false, PILOT_ALLOWED=false. Старі BATCH/PLAN-TIME PASS — історичні для попереднього runtime, не повне приймання цього кандидата. Shared-DB tenancy, GPT adapter/live API та клієнтські конектори не реалізовані цією карткою. Sites v3/sourcece032203 лишився окремим і незміненим; dirty UAH Site не переносився як фінансова модель.

Після цього checkpoint автономно виконуються новий локальний browser runner і дозволені standalone empty migrations/current access sweep. Уточнення A11 дозволяє новий локальний runner; старі cloud-CDP/CDN/loopback обходи заборонені. Same-N restore — окрема підготовка в POSIX. P05 3/3 лишається; full/postgres/e2e/windows presets, A09 targeted13MiB та A10 activation/upgrade/rollback не запускаються автоматично. 11 початкових критеріїв незмінні. Після готового кандидата потрібен конкретний пакет рішення щодо останнього full acceptance, без підміни історичного ліміту.
