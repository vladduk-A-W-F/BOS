# A10: контрольоване завершення Waitress

Дата: 12.09.2026. Зміни лише у новому `tmp/a10_drain_draft`; основний checkout не змінювався. Усі HTTP-запити й SQLite — нові власні синтетичні ресурси. Відомі відмови A09 13 MiB не повторювалися й не переглядалися як прийняті.

## Факти перед зміною

У встановленому Waitress 3.0.2 `server.run()` перехоплює KeyboardInterrupt та викликає shutdown. `ThreadedTaskDispatcher.shutdown(cancel_pending=True)` повертає True після очікування, навіть якщо потоки ще залишилися. Тому булеве повернення та exit 0 старого runner не доводять завершення записів.

Це відтворено справжнім WSGI/HTTP-процесом з A09 control flow: один запит залишався утриманим. Після двох штатних очікувань по 5 секунд процес видав `shutdown_result=true`, `active=1`, `dispatcher_threads=1`, завершився 0 і перервав HTTP без завершення запису. Це реальний red, а не припущення з коду або замоканий dispatcher.

## Що змінено у драфті

Runner використовує власний `wasyncore.loop(count=1)` і обробляє SIGTERM/SIGINT через Event. При drain закривається тільки listener; trigger та канали з прийнятими запитами залишаються для завершення роботи й відправлення відповідей. Нові/неповні запити більше не читаються в dispatcher. Повністю прийнята черга завершується.

Власний підклас dispatcher зберігає реальні Thread objects. Черга та active counter перевіряються під власним lock. Лише після нульових queue/active/pending requests/output workers отримують команду stop, кожний реальний thread очікується через join. Trigger і решта власного socket map закриваються після цього.

Єдина успішна квитанція:

```json
{"event":"bos.server.quiescent","runtime":"waitress","runtime_version":"3.0.2","active":0,"queued":0,"workers":0,"sockets_closed":true,"version":"0.2.9-dev"}
```

За timeout видається `bos.server.drain_failed`, exit **6**, без quiescent. Булевий результат бібліотечного shutdown не використовується. Сам runner не видає maintenance lease. Lifecycle має приймати квитанцію лише від конкретного власного Popen і вимагати завершення обох власних процесів 0 без forced stop; це окрема інтеграція control agent.

Canonical `serve` зберігає попередній порядок: server WSGI/config validation і pin Waitress перевіряються до створення потоків чи сокетів. CLI додає лише `--drain-timeout`, типово 5 секунд, скінченне додатне значення до 120.

## Фактичне приймання драфта

`tmp/A10_DRAIN_ACTUAL_1.json`: **3/3 сценарії**, один скінченний прогін.

| Сценарій | Результат |
|---|---|
| A09 legacy held request | False-success відтворено: shutdown True, exit 0, active/thread залишилися, HTTP перерваний. |
| A10 4 active +1 queued | Перед release реально спостерігали active=4, queued=1; нові TCP connect відхилені. Усі 5 SQLite commits і точні HTTP200 responses завершено; quiescent містить нульові лічильники, exit 0. |
| A10 held timeout | Exit 6, активний запит у failure snapshot, quiescent відсутній. Після завершення процесу пізня release не змінила SQLite. |

## Файли для інтеграції

Manifest: `tmp/A10_DRAIN_FROZEN.json`. Усі три файли read-only.

- `tmp/a10_drain_draft/start_server.py` → `scripts/start_server.py`; SHA256 `f25b421aa9f5c2542ebecbe5cea3f6a70bad25d6bbfb8e27accbe01e3eced6c6`.
- `tmp/a10_drain_draft/held_wsgi_process.py`: реальний synthetic WSGI subprocess fixture; SHA256 `cb48275769c6e3ea2a2a5b933d22330f1b802e73ef3706ab297e0dc6395d553e`.
- `tmp/a10_drain_draft/drain_probe.py`: відтворення трьох сценаріїв; SHA256 `60b0e959f3ed09d2668f564f8d02a7ce38fc9c5c1ee9012ccdbfd98155fb2782`.

Це вузьке приймання runner drain. Backup/restore, maintenance lease IPC, production install, PostgreSQL, Windows, зовнішній CI та повні 11 gates цим прогоном не закриваються.
