# A09 · незалежний перегляд installer / provisioner

12.09.2026. Обсяг: `a09_install_server.py`, `a09_provision_runtime.py`, авторські bootstrap тести та протокол нової інсталяції. Усі відтворення виконані на власних нових тимчасових каталогах. Вихідний checkout, клієнтські бази й документи не змінювалися. Мережевих підключень і SQL у цих відтвореннях не було; у дофіксовому offline кейсі створився лише власний порожній файл DB перед очікуваною відмовою синтетичного пакета.

## Підтверджені проблеми та мінімальні зміни

| Межа | Фактичне відтворення до зміни | Зміна |
|---|---|---|
| Незмінний вхідний пакет | `registry=source/installer-registry` прийнято; у source з'явилися REGISTRY.json, lock і запис із секретом | Попарне невкладення всіх трьох шляхів до створення registry або target |
| Стандартний Python bootstrap | Власні `venv.py` та `pip.py` у release реально виконалися через `cwd=release` | Python `-I` для stdlib venv, pip і незалежного metadata probe; Django далі працює з потрібним release |
| Чужі байти через hardlink | Після справжнього failed pip власний venv executable hardlink прийнято; resume перезаписав сторонній синтетичний файл Python ELF, 30 894 944 bytes | Кожен regular файл усередині owned runtime tree повинен мати `st_nlink=1`; спеціальні файли також відхиляються перед subprocess. Права executable не змінюються |
| Завершена інсталяція | Запис з `application_provisioned=true` допускав повторний bootstrap і фактичний запуск venv/pip | Рання відмова resume у `prepare_install` до створення/зміни runtime; окремий read-only lifecycle loader відповідає за start |
| Offline та закріплені залежності | Synthetic wheel з `Requires-Dist: ... @ file:///.../outside-wheelhouse/...whl` встановив незакріплену залежність поза wheelhouse; pip check і перевірка лише очікуваних версій пройшли | Локальний wheelhouse має бути каталогом; pip додає `--no-deps --only-binary=:all:`. Усі залежності потрібно явно закріпити, а неповний граф відхиляє чинний pip check |

`--no-index` саме по собі не означає відсутність URL resolution. Контрольний wheel містить тільки синтетичні metadata файли; `.pth`, import-коду чи виконуваного payload немає. Виправлена версія встановлює лише явно закріплені synthetic Django/Waitress, відмовляє на pip check через пропущену зовнішню залежність та не створює DB.

## Перевірки та збережені перші результати

- `A09_INSTALLER_INDEPENDENT_BEFORE.json/.log`: фактична зміна source та запуск пакетного venv.py.
- `A09_INSTALLER_HARDLINK_BEFORE.json/.log`: actual resume і перезапис власного стороннього canary у Python ELF.
- `A09_INSTALLER_REVIEW_REGRESSION_BEFORE.log`: 5 методів, 8 відмов. Одна з них була помилкою harness: повертався перший record реєстру замість конкретної компанії. Це не зараховано як дефект застосунку. Harness виправлено точним збігом root.
- `A09_INSTALLER_HARDLINK_TEST_BEFORE.log`: після виправлення harness окремий hardlink кейс дійсно червоний — `inspect_partial` не відхиляє hardlink. Попередній окремий actual overwrite proof незмінений.
- `A09_INSTALLER_REVIEW_REGRESSION_AFTER.log`: початкові 5 методів пройдені, 7.071 с; є машинні факти для кожного кейсу, зокрема незмінність компанії B при відмові компанії A.
- `A09_INSTALLER_ORIGINAL9_AFTER.log`: 9 авторських bootstrap методів пройдені на fixed installer, 0.129 с. Від попереднього запуску цього набору installer більше не змінювався.
- `A09_INSTALLER_OFFLINE_BEFORE.json/.log`: фактично встановлено `synthetic_outside` із file URL поза wheelhouse.
- `A09_INSTALLER_OFFLINE_AFTER.json/.log`: результат повтору цього самого bounded proof із новим provisioner.
- `A09_INSTALLER_REVIEW_REGRESSION_FINAL.log`: остаточні 7 методів із реальними venv/pip та JSON-фактами кейсів.

Команди виконувались `/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python`. Постійний regression harness — `tmp/a09_install_server_review_tests.py`; fixed drafts — `tmp/a09_installer_review_fixed/`. Для дофіксового запуску harness передається `BOS_REVIEW_DRAFT_DIR=/workspace/scratch/c7b51e996a9f/tmp`; за замовчуванням він читає fixed drafts. Під час інтеграції root має прив'язати імпорти до canonical scripts, без tmp залежності.

## Межі висновку

Довірений приватний реєстр, exclusive creation, точні контрольні байти, перевірки root/DB inode, попарне невкладення компаній і фактичний advisory lock утворюють послідовний механізм продовження власної незавершеної інсталяції. Чужа порожня ціль, змінений config, copied marker та підмінений root відхиляються. Автоматичного видалення чужого bundle немає. Crash між mkdir і registry commit лишає відому явну відмову наступного запуску; це не автоматичний repair.

Реєстр — довірений адміністративний стан. Цей модуль не захищає від адміністратора, що одночасно зловмисно переписує сам реєстр, код і всі каталоги. Self-hashed `BOS_PACKAGE.json` доводить незмінність та повний склад пакета відносно наданого manifest; він не є цифровим підписом автора. Код і wheels мають походити з явно довіреного оператором релізу. Новий механізм PKI чи мережевий package downloader не додавався.

Тут не виконувалась повна установка 33 справжніх залежностей, Django migrate/collectstatic або TLS на **новому fixed SHA**. Авторські старі actual installation звіти належать попередньому SHA. Перед complete потрібні новий canonical пакет, справжня установка цього пакета та root HTTP/TLS приймання. Поточний висновок обмежений перевіреними installer trust boundaries; загальний A09 gate 8 ним не закривається.
