# A10: кероване обслуговування в тому самому процесі

Це окрема основа для перевірки резервування. Вона не керує іншою вже запущеною програмою через мережу чи IPC. Unix transport фактично заблокований середовищем (`AF_UNIX → EPERM`) і лишається НЕ ЗАПУЩЕНО; socket/FIFO/file-command заміни не додавалися.

## API

Канонічний кандидат: `scripts.maintenance_control.ManagedSupervisor` та точний клас `QuiescenceLease`.

```python
runtime = BoSRuntime(
    installer=installer, target=bundle, registry=registry,
    installation_id=installation_id, caddy=caddy,
    certificate=certificate, private_key=private_key,
    ca_certificate=ca_certificate, http_port=http_port,
)
with ManagedSupervisor(
    installer=installer, target=bundle, registry=registry,
    installation_id=installation_id, start_callback=runtime,
) as supervisor:
    supervisor.start()
    lease = supervisor.quiesce(operation_id)
    with lease.fenced_for(installation_id, bundle, operation_id):
        capture_callback(lease)
    lease.release()
```

`capture_callback` — довірена функція того самого процесу. Приклад не реалізує backup сам по собі. Реальні native backup/restore та їхні acceptance gates готує root окремо.

`BoSRuntime` має параметри `installer,target,registry,installation_id,caddy,certificate,private_key,http_port,ca_certificate=None,startup_timeout=20,emit=None`. Він використовує чинні A09 loader/config/proxy/health, закріплені Waitress 3.0.2 та Caddy 2.11.1 і A10 drain runner. Обидва children створюються лише `owner.spawn`; Caddy додається другим, тому зупиняється першим. Callback повертається після actual owned-Caddy startup event та двох перевірених HTTPS health відповідей. Raw proxy stdout/stderr не зберігається: лише canonical allowlist normalizer.

Для іншого довіреного callback доступні `owner.spawn(name, argv, **popen_options)`, `owner.track_reader(thread, streams=(...))`, `owner.record_drain(actual_process_handle, event)`. Тестовий `wsgi_fixture.py` показує реальний pinned Waitress adapter. Callback повинен сам виконати реальну перевірку свого startup; `ManagedSupervisor` додатково перевіряє, що всі власні children живі. Це не публічний API для приймання чужого serialized «успіху».

## Дозвіл і межі

Supervisor утримує instance flock весь час життя owner object. Lease зв'язаний з точним owner object, поточним процесом, installation UUID, root inode та operation UUID. Перевіряються приватні контрольні файли, inode DB й runtime root. `/proc/self/fdinfo` підтверджує FLOCK саме відкритого fd; inode або присутність lock-файла самі по собі не вважаються доказом. PID namespace враховується через власний `/proc/self/status`.

`quiesce(OP)` видає capability тільки після припинення власних children, exit 0 без force та справжнього `bos.server.quiescent` із stdout **свого** Waitress Popen: active=0, queued=0, workers=0, sockets_closed=true. Timeout або відсутній drain receipt — стан failed, lease не видається. Незалежний Waitress proof також перевіряє закінчення 4 active + 1 queued HTTP запитів і записів до acknowledgement.

`lease.assert_for(ID, root, OP)` / `assert_live()` перевіряють живу object authority, фактичний lock fd, відсутність власних активних дітей і state=quiescent. Прив'язки доступні тільки для читання. Закритий owner, розблокований fd, інша установка/операція та старий lease після release не приймаються.

`fenced_for(...)` утримує owner RLock протягом callback і не дає паралельному release стартувати writers. Він не бере generation ledger lock і не читає/змінює його pointer. За використання ledger порядок такий: його наявний flock → owner RLock. Нових дій activation цей прототип не виконує.

`release()` повторно запускає лише попередній N. Наявність `generations/ACTIVE.json` забороняє initial start і release старого N; quiescent дані не перемикаються мовчки. Запуск N+1 не реалізований і не заявлений. Відокремлені процеси не можуть передати такий lease один одному; для окремо працюючого supervisor потрібний інший, ще не перевірений контрольний механізм.

## Фактична перевірка

`A10_INPROCESS_CONTROL_RESULT.json` та `A10_INPROCESS_CONTROL_ACTUAL_2.log` — 10 пройдених скінченних перевірок на власному Linux/Python/Waitress стенді. Серед них: справжній held HTTP write до acknowledgement, HTTP 200 і committed SQLite row, lifetime flock/double owner refusal, actual unlocked-fd refusal, concurrent release fence, same-N restart, lease revocation, ACTIVE pointer refusal, timeout exit 6 без lease і без відкладеного запису.

BoS test DB залишилася байтово незмінною. Усі тестові діти зупинені. Unix drafts та їхній blocker збережені окремо. Адаптер `managed_runtime.py` для повного BoS/Caddy підготовлений, але на момент цього документа його actual Django package proof ще виконує root; він не підміняється успіхом WSGI fixture. Критерії 7/9, restore, upgrade, production, PostgreSQL та Windows цим звітом не закриваються.

Незалежний reviewer a09_server_review прочитав exact control SHA 4e9b3305… та adapter SHA 85e9ad9d… і actual 10-check звіт. У межах same-process capability blocking defect не знайдено; досягнуто scoped source consensus. Це не розширює статус IPC, daemon або acceptance gates резервування/відновлення.
