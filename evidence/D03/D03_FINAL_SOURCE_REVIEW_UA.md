# D03 · остаточний незалежний source review

Дата: 12.09.2026. Перевірено заморожений `tmp/d03_final_candidate/MANIFEST.json` SHA **`5ccd5e214efed0a0b0ccbc50737a9d7ac3117ab4900afe974c1d63578c312211`**, рівно 22 файли. База у manifest — C03 source `7be2d6ba56ff8d99198645ffe7e1bb5b16d7ad0c37ca72e53b8f3c410dfe8011`.

**Висновок: консенсус щодо цього набору змін документації, прикладів, версії та одного тексту UI. Нових блокувальних розбіжностей у final delta не знайдено.** Усі 22 candidate SHA та відповідні base SHA/ознаки нового файла збіглися; файлів поза manifest немає. Остаточна інтеграція й заповнення підсумкових evidence належать root. F04 як продуктова умова першого серверного входу залишається відкритою.

Це читання коду/документів, byte-diff і SHA, не виконання інструкцій. Тести, браузер, API, Python/Django-застосунок, CSV parser, сервер або БД не запускалися. Бази, приватні документи й backup не читалися. Canonical і final candidate не змінено.

## Final delta проти попередніх review

| Частина | Перевірений результат |
|---|---|
| TEST_REPORT / F03 / F06 | `docs/TEST_REPORT_UA.md:7–19` використовує актуальні wrapper-команди й підготовлене середовище. Bash `BOS_PYTHON` та передавання аргументів відповідають `scripts/verify.sh:1–6`; файл executable 0755. PowerShell **-Suite/-Python/-Output** точно відповідають `scripts/verify.ps1:1–10`. Старі standalone-команди більше не пропонуються для чистого архіву. Історичні JSON і старий звіт відокремлені в `:25–31`; старе «зміна строку не реалізована» не видається за сучасний C01. |
| TEST_REPORT:35–37 / межі | Linux/Python/Django/SQLite названі локальною базою перевірки. SQLite conflict явно не підміняє PG row-lock waiting; Babel/Node/PDF не підміняють browser acceptance. A09/A10/A11/F04 й зовнішні системи залишаються відкритими. Текст не обіцяє full exit0. |
| SERVER_INSTALL / F04 | `docs/SERVER_INSTALL_UA.md:58–60` прямо вказує відсутність автоматичного технічного акаунта та підтриманого operator bootstrap CLI. Звичайний `manage.py` без приватної installation-конфігурації не пропонується як готовий шлях. Наявність Django-команд не видається за прийнятий перший вхід клієнта. **Інструкційна неоднозначність закрита; продуктова відсутність CLI не виправлена.** |
| ERP_GUIDE / F08 / replay | `docs/ERP_GUIDE_UA.md:20,42` додає Керівника, джерельні дозволи й свіжий synthetic набір; розрізняє перше виконання і повтор проведеного наміру з поточними правами. Unknown reply не перетворено на дозвіл нового intent. `:102` направляє до фактичного C03 RESULT та окремих manual/E2E прикладів, без змішування старих 21 операції SO-101 і 14 дій нового gate6. |
| PARAMETERS / F05 / F07 | `docs/PARAMETERS_UA.md:8,24–31` розрізняє Django User/групу/Employee та навчальний акаунт; активний BoSHome бере ERP snapshot, старий branches/demo позначений історичним. 20 000 operations-only та 21 600 стандартного повного seed прямо розмежовані; 24 000 Configuration.cash не названо C03-журналом чи банківським залишком. |
| KNOWLEDGE / A01 | `docs/KNOWLEDGE_UA.md:15`: «резервування понад доступний запас» замість загальної заборони подвійного резервування. Це відповідає `erp/service.py:97–99,269–279`: нові Reservation дозволені в межах вільної кількості; кілька законних резервів не оголошуються дефектом. |
| WRITE_PATHS / frozen inventory | `docs/WRITE_PATHS_UA.md:303–308` — лише доданий appendix F04. Весь попередній файл є незмінним byte-prefix. База85/12 не перенумерована; F04 не названо новим грошовим/складським writer. Оцінка0,5–1,5 людино-дня позначена попередньою, після блоку3, без дати релізу або виконаної реалізації. |
| Раніше перевірені root docs | README/ACCESS/BACKUP_RESTORE/DEMO_AND_IMPORT/MVP/STATEMENTS відповідають погодженим чернеткам. NEXT_STEPS містить прийняте уточнення «резервне копіювання та відновлення в нову керовану установку». Колишнього manifest mismatch більше немає. |
| Рольові посібники | ROLE_GUIDE змінено тільки на 0.2.16-dev та додано PDF-посилання/пояснення короткого витягу; тіла ролей незмінні. CAPABILITIES — тільки версія та синхронізована фраза про «Про систему». DEMO_30_MIN, STATEMENT_DEMO і CSV **побайтово збігаються** з незалежно перевіреним e241a6de draft. Попередній role/source/numeric висновок переноситься без нових поведінкових перевірок. |
| UI й версія | JSX та app.js точно збігаються з уже перевіреним `tmp/d03_ui_copy`: source `217ef22b…`, app `0285afed…`. Це та сама одна заміна текстового абзацу; actions/guards/source/dialogs незмінні. `boss_project/version.py` має рівно заміну 0.2.15-dev→0.2.16-dev. HTML не потребує зміни й до22files не включений. |

## PDF: перевірений ланцюг походження, без повторного рендеру

`tmp/pdfs/ROLES_PDF_QA.json` SHA **`7368a17fb91cfc7fe292c1c5e2f1fe91a128c6a8b2163cc15f83198728b7be36`**. Його source SHA збігається з перевіреним role draft `32cee324…`. SHA PDF у QA, `output/pdf/BoS_Roles_UA.pdf` та final `docs/BoS_Roles_UA.pdf` однаковий: **`e87c6f44737de19fd5fa618554317f5da0c129c5a70825f983bdd9747d558a01`**.

QA root фіксує 3 фактичні сторінки, по1 на CEO/manager/observer, і власний візуальний перегляд без обрізання/накладання. Цей reviewer незалежно звірив байти/походження; PDF не рендерив і не видає root-візуальний огляд за власний. Final ROLE_GUIDE правильно називає PDF **коротким витягом**, а спільні правила й приклади лишає у Markdown. Рольові тіла джерела не змінені.

## Залишки інтеграції та межі погодження

1. Root інтегрує D03 лише після окремого C03 commit. Погодження цих22files не є доказом їх уже виконаної інтеграції або нового повного verify на D03 source.
2. На момент читання відсутні **4 різні цілі посилань**, очікувані за планом root: `evidence/C03/RESULT_UA.md`, `evidence/D03/RESULT_UA.md`, `evidence/D03/D03_OPERATOR_BOOTSTRAP_UA.md`, `evidence/D03/history/TEST_REPORT_UA.md`. Вони згадані в ERP_GUIDE:102, SERVER_INSTALL:58, STATEMENTS:5, TEST_REPORT:25,28–29, WRITE_PATHS:308. Їх треба додати до остаточного пакета; це не приховані broken links. Усі інші явні локальні Markdown-посилання мають цілі в final/canonical overlay.
3. Історичний TEST_REPORT слід зберегти побайтово під новим evidence-шляхом, SHA початкового файла **`821af2f05a63d5ce1438440840fe008922a79c76523b87c98553f3bcba97bf38`**. Новий опис навігації не доводить, що це копіювання вже виконано.
4. Root повідомив actual full26 gate6 821/42 на C03 source; цей bounded review не перечитував його runtime-доказ і не переносить результат на новий D03 source. Native/install на момент призначення ще виконувалися. Заплановані PROGRESS/CHANGELOG/evidence/D03 мають назвати тільки фактичні підсумки.
5. F04 лишається явною відкритою умовою першої серверної установки. A09 oversize, A10 upgrade/rollback, A11 browser/Windows, PostgreSQL/зовнішній CI та людське приймання не закриті документами. Тут немає дозволу на нові платні/публічні дії, вигаданий bootstrap або зміну11gates.

Окремих нових тестів або розширення продуктових прав для погодженого final delta не потрібно. Завершальна робота root — exact integration, наявні цільові evidence, поточний статус і належна фіксація proof scope.

## Опорні попередні review

- `tmp/D03_DOCUMENTATION_FACT_AUDIT_UA.md` — первісні F01–F08.
- `tmp/D03_ROOT_DRAFT_REVIEW_UA.md` — основні root docs та exact UI text/compiled diff.
- `tmp/D03_ROLE_GUIDE_REVIEW_UA.md` — ролі, поточні/історичні source guards, ручний CSV і numeric E2E oracle.

Перелік усіх22files з base/final SHA залишається у перевіреному immutable manifest `5ccd5e21…`; тут він не переписаний іншим інвентарем.
