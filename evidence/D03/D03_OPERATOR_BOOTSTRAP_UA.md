# D03 · перший адміністратор серверної установки

**F04 підтверджено: безпечний операторський bootstrap ще не має завершеної підтриманої команди.** Штатні Django management-команди існують, але наявні BoS CLI не завантажують приватну конфігурацію конкретної установки для їх виконання. Це не готова перевірена інструкція створення першого адміністратора.

Огляд 12.09.2026 — тільки статичний код і документація. Команд нижче не виконано; конфігурації, секрети, БД і файли фактичних установок не відкривались. Новий wrapper не створювався. Це не повтор activation/upgrade або A09 експерименту.

## Що вже існує

| Елемент | Точне місце та поведінка |
|---|---|
| Приватний Python | target/venv/bin/python, створений provisioner для Linux |
| Власний код | target/releases/source_sha256/manage.py; SHA — з результату власної установки, не довільний latest |
| Серверний профіль | Модуль server_settings, файл у корені release. Це не boss_project.server_settings |
| Конфігурація | target/config/server.json; формат задає scripts.install_server.artifacts(record). Містить приватний секрет та точні UUID/root/database/media/origin/hosts/proxy peers |
| Перевірений loader | scripts.lifecycle_server.load_owned(installer, target=…, registry=…, installation_id=…) перевіряє trusted registry, inode, provisioned runtime, code manifest і config bytes; повертає record/release/python/config |
| Середовище дитини | scripts.lifecycle_server.child_environment(config) прибирає сторонні BOS/PYTHON/loader змінні та передає конфігурацію дочірньому процесу; не є CLI-командою |
| Блокування установки | scripts.lifecycle_server.instance_lock(installer, target) відмовляє другому власнику; також внутрішній helper |

server_settings.py викликає from_environment(BASE_DIR) і **не читає JSON сам**. Потрібні чинні DJANGO_SETTINGS_MODULE=server_settings, BOS_DATA_MODE=working, BOS_DATABASE_ENGINE=sqlite3, BOS_INSTALLATION_ID, BOS_INSTALLATION_ROOT, BOS_DATABASE_PATH, BOS_MEDIA_ROOT, BOS_PUBLIC_ORIGIN, BOS_ALLOWED_HOSTS, BOS_TRUSTED_PROXY_IPS, BOS_SECRET_KEY. Вони мають походити з перевіреної конфігурації цієї установки, а не з вигаданих прикладів чи ручної заміни секрету.

## Точні наявні management-команди

Нижче **частини команди**, а не самодостатній bootstrap. Їх можна виконувати лише після підтриманого завантаження перевіреного installation environment, якого наразі бракує в операторському CLI. SOURCE_SHA256, USER_ID та EMPLOYEE_ID в кутових дужках — заповнювачі фактичних значень.

Створення першого технічного адміністратора:

    /srv/bos-company/venv/bin/python /srv/bos-company/releases/<SOURCE_SHA256>/manage.py createsuperuser --settings=server_settings

Це стандартна команда Django. Її код перевірено статично: інтерактивний режим читає пароль через getpass і створює superuser; --noinput не додається. Пароль не передається в аргументах або в документі. Виконання цієї команди на власній новій BoS server installation у межах F04 ще не перевірено.

Явна прив’язка вже створених бізнес-акаунта та співробітника:

    /srv/bos-company/venv/bin/python /srv/bos-company/releases/<SOURCE_SHA256>/manage.py link_bos_user --settings=server_settings --user-id <USER_ID> --employee-id <EMPLOYEE_ID>

link_bos_user приймає саме два обов’язкові числові IDs. Він не створює User або Employee, не призначає групу, пароль чи permissions і не перетворює працівника на CEO. Під transaction.atomic команда перевіряє існування обох записів, зберігає історичні IDs; той самий зв’язок повторно не змінює стан, інший зв’язок відхиляється. Новий зв’язок створює AuditEvent identity.link. Поле Employee.user у native admin readonly, тому цей крок не підміняється ручним редагуванням форми.

Після доступного bootstrap технічний адміністратор використовує /admin/: окремий технічний акаунт без бізнес-груп; бізнес-користувачеві — рівно одна з ceo, manager, observer, потрібні permissions документів/експорту і, за потреби, фактичний Employee. Посада Employee та is_staff/is_superuser не замінюють бізнес-групу. link_bos_user не перевіряє архівний стан сама; runtime actor_for_user відмовляє доступу прив’язаного архівного співробітника. Автоматичного створення бізнес-ролей/співробітників першою командою немає.

## Чого саме бракує

install_server виконує provision; lifecycle_server — serve; maintenance_server має backup/serve/restore. Жоден із цих CLI не має admin, manage, createsuperuser або passthrough підкоманди. Вкладений provision_runtime.run викликає лише фіксовані check/migrate/collectstatic/proof кроки і захоплює stdout/stderr; він не є інтерактивним інструментом оператора.

Звичайний python manage.py createsuperuser непридатний як інструкція для цього пакета: manage.py за замовчуванням обирає boss_project.settings, а не приватну установку. Додавання тільки --settings=server_settings не заповнить installation environment. Не слід вигадувати --config server.json, запускати JSON як shell-файл, друкувати/копіювати його секрет через shell expansion або подавати неперевірений Python heredoc як уже підтриманий BoS launcher.

Отже **F04 не закрито лише документацією**. Мінімальний відсутній продуктовий крок — окремий перевірений операторський шлях до наявних двох management-команд: власний target/registry/UUID → наявні ownership/config helpers → приватний runtime та робочий профіль → інтерактивний terminal для пароля; з відмовою для чужої/підміненої або зайнятої установки. Конкретний інтерфейс такого шляху тут не вигадується й не реалізовується. Після його фактичної реалізації потрібен власний synthetic bootstrap proof, тоді D03 може дати одну завершену копійовану команду.

До цього SERVER_INSTALL має явно зазначити: «Після provision технічний адміністратор автоматично не створюється. Безпечний CLI bootstrap першого адміністратора для приватного server profile ще не реалізований і не прийнятий». Наявні internal helpers доводять можливість мінімальної доробки, але не готовий onboarding клієнта.

## Прив’язка до source

Перелік SHA додається нижче. Стандартний createsuperuser прочитано зі встановленого Django у reviewer runtime; команду та Django setup не запускали. Canonical файли незмінні.

| Прочитаний файл | SHA-256 |
|---|---|
| manage.py | 3e985fb40263d48efe40b95c974b8bac8b291a9fadd9d8345f7e36873e40b9c9 |
| server_settings.py | 964f1cdc063ec2593e307ae5be15ad546c2295a57f979cfb981d6a54eea99bf7 |
| boss_project/server_config.py | 436ef83fa1b85e6924c153ad60d34d17696219cffd460abab8713bced044dd0a |
| scripts/install_server.py | 9db968c6611971378a782433396441656fe1bd1659783be1eb86d219db85deea |
| scripts/provision_runtime.py | 0b6f2c1ebc6cf80bd0e70c65b04314645c6e2c7c93ee35dff8291a95ff1a47b0 |
| scripts/lifecycle_server.py | e21fa92d85715bad84e8a37b9fc50545bce4044eea0107bbc98e9009315b8f5e |
| scripts/maintenance_server.py | 0986f037cf99f9ada33e58716f40d8c407b415f039d936ce145e60215e12ebb5 |
| employees/management/commands/link_bos_user.py | f80192520df497ea667b63042a78087620d6fbc69c39d025bce3bbebc627c6d0 |
| employees/admin.py | 2ad2986124563a04c188c70c4dd0fc770e2e4fe5206c39311b4a146af4315689 |
| boss_project/identity.py | a5cdff7a921aa8e2b9802af19c866118285307061efcde8e0ec6514dd5466738 |
