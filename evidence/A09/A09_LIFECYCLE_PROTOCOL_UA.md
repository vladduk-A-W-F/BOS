# A09: локальний запуск однієї власної інсталяції BoS

Статус: кандидат для інтеграції root. Це foreground supervisor для локального HTTPS стенду. Публічний сервер, Windows, оновлення, backup/restore та production acceptance цим документом не підтверджуються.

## Межі власності

`scripts/lifecycle_server.py` отримує bundle, зовнішній довірений registry та виданий ним installation UUID. Перед запуском звіряє root inode, точні байти контрольних файлів, зареєстровані runtime roots, inode приватної SQLite, незмінний release manifest та відсутність сторонніх hardlink/symlink у venv. Законні бізнес-файли в `state/private` не вважаються пошкодженою незавершеною інсталяцією, не змінюються і не видаляються.

OS flock у `runtime-logs/INSTANCE.lock` утримується весь час роботи supervisor. Повторна команда тієї самої інсталяції відмовляє до запуску серверів. ID іншої зареєстрованої компанії не може обрати цей bundle. Реєстр — приватний стан довіреного оператора; його власноручна підміна тим самим системним користувачем не є окремою межею безпеки.

## Команда запуску

Після фактичного offline provision застосунку:

```sh
python scripts/lifecycle_server.py \
  --target /absolute/company-bundle \
  --registry /absolute/operator-registry \
  --installation-id UUID_FROM_INSTALLER \
  --caddy /absolute/verified-caddy \
  --certificate /absolute/server.crt \
  --private-key /absolute/server.key \
  --ca-certificate /absolute/local-ca.crt \
  --http-port 18080
```

HTTPS origin та порт беруться з `config/server.json`. `--ca-certificate` потрібний для явно довіреного локального CA; без параметра використовується системне сховище довіри TLS. Приватний ключ повинен бути окремим звичайним файлом mode 0600. Сервери слухають лише 127.0.0.1. HTTP та HTTPS порти різні; незайнятий upstream порт призначає сам Waitress.

Відсутній TLS або proxy не перетворюється на успіх. Кандидат перевіряє точний SHA Linux amd64 Caddy 2.11.1 і його фактичну версію. Waitress підтверджує runtime 3.0.2 через stdout подію. Секрети конфігурації передаються середовищем, не аргументами командного рядка.

## Події та завершення

`bos.bundle.ready` друкується тільки після справжніх GET `/health/live/` та `/health/ready/` через HTTPS із перевіркою довіри сертифіката і hostname. Подія містить installation_id, origin, scope=loopback, health={live:200,ready:200}, source_sha256, runtime, proxy, upstream_port. Це готовність активного локального процесу, не загальний сертифікат готовності релізу.

SIGINT або SIGTERM supervisor завершує лише дочірні процеси, створені його власними Popen handles, і друкує `bos.bundle.stopped` з exit codes та ознакою forced. PID-файл не дає дозволу вбивати процеси; окремої команди kill/stop за довільним PID немає. Exit 0 означає звичайне завершення обох дітей без forced kill. Помилка старту, чужа інсталяція, зайнятий порт або дубль мають exit 3 і `bos.bundle.refused` з complete=false. Сторонній процес, який займає порт, залишається недоторканим.

Caddy stdout і stderr читаються через pipe та перед збереженням проходять `boss_project.proxy_logging.write_proxy_line`. У журналі залишаються лише event, status, version та згенерований correlation_id. Немає raw fallback, запиту, шляху, заголовків, довільного msg або exception. Помилка нормалізації/запису зупиняє supervisor. Waitress має свій окремий канонічний application logger.

## Фактичні докази

Перший immutable синтетичний пакет `1fea0cca612ce53cf219a62ad4055ff1124e0246a5cf207a58c472de4fe88cd3` дав вісім реальних сценаріїв: offline чистий runtime+міграції+статика, missing TLS refusal, HTTPS health, конкурентна CLI відмова, інший company ID, clean stop усіх портів, restart із незміненим бізнес-файлом, зайнятий порт зі збереженим стороннім listener. Обидві нормальні зупинки дали Caddy=0, Waitress=0, forced=false. `A09_LIFECYCLE_RESULT.json` та `A09_LIFECYCLE_ACTUAL.log` зберігають точний stand.

Додатковий `A09_LIFECYCLE_FINAL_RESULT.json` довів фактичний red попереднього loader без обов'язкового venv ownership proof, refusal нового loader, refusal hardlinked executable, реальний HTTPS, дубль і clean stop. Цей доказ стосується SHA 194fc1c8… до додавання proxy log normalizer.

Фінальний normalizer + fixed installer/provisioner фактично пройшов дев’ять сценаріїв на новому immutable пакеті `9e0c71d5a28b2699d566c5a620279388b9aae88276480bb38dcb8284c08268af`. Результат — `A09_LIFECYCLE_NORMALIZED_RESULT.json`: усі 33 закріплені залежності, 65 реальних proxy log lines лише з чотирма дозволеними полями, приватний canary відсутній.

Додатково відтворено хибну ready подію, коли порт займав власний тестовий сторонній сервер із дійсним TLS. `A09_LIFECYCLE_FOREIGN_TLS_BEFORE.json` фіксує red з першої спроби. Кандидат тепер чекає внутрішню startup Event від свого Caddy (точне повідомлення pinned процесу читається лише в пам’яті) та повторно звіряє життя дітей після health і перед ready. `A09_LIFECYCLE_OWNED_READY_FINAL.json` підтверджує три відмови без жодної ready події, збережений сторонній процес, нормальний власний HTTPS start, duplicate refusal та clean stop Caddy=0/Waitress=0. Фінальний launcher SHA `e21fa92d85715bad84e8a37b9fc50545bce4044eea0107bbc98e9009315b8f5e`; останній proof виконував цей точний зовнішній кандидат над своїм незмінним пакетом 9e0c71…, не переписуючи manifest. Root має повторити canonical check_install після остаточної інтеграції всіх A09 файлів.
