# B30-PREVIEW-DELIVERY-PREP: независимое ревью

27.09.2026. Подготовка, не выполнение. Автор bos3_fixture_impl; независимый reviewer start_overview_review; интегратор root.

Вердикт: ACCEPT_SCOPED_STATIC. Точный кандидат f55a15de4006d10c0d7c65f8a2ca8499fbb99819, исходный runtime 33d7d387aa582c04339a91ae94361948ea67904c. UI commit aee8d0ee41afd5cba256a0b4a4deddadf7af6e4e является предком кандидата, exit 0.

## Проверенные файлы

- maintenance_light_preview.py: SHA-256 F09599F6DB7B1FF0951DB0D9BD66692DB1F1A0C1A7EB597252A524E7295502A7.
- README-notes.md: SHA-256 600579692883E2826A3538D24F8693572112C2A5426E06D68D98B473FD9299EF.
- Предыдущий reviewed runner: evidence/entry-delivery-20260927/maintenance_frontend_delivery.py, SHA-256 09ED0A9F1B535C6607FE82D3BB71689EC1259DDBC4C527FC206710E03359AF57. Его старый target не применять для dev.3.

Reviewer независимо сопоставил Git diff между указанными commits: ровно 12 продуктовых файлов из LIGHT_PREVIEW_CANDIDATE.json, остальные изменения только в docs/orchestration/**. Изменения runner ограничены immutable target, двумя README в allowlist и отдельными именами evidence. diff --no-index exit 1 означает ожидаемое наличие этих различий, не ошибку исполнения runner.

Сохранены проверки чистой runtime-копии, baseline/candidate/ancestry, точного source/digest/SQLite binding, Git PNG signature, loopback listener и PID receipt, остановленного состояния перед apply, неизменности data/media/credentials и атомарного обновления только prepared.source_sha256. Runner не выполняет lifecycle-команды, init, seed, migrate, reset или rollback.

## Граница допуска

Не выполнялись даже --help, capture или apply. Сервер, HTTP, браузер, БД и секреты reviewer не открывал. Runtime остаётся dev.1. Требуется точный ответ владельца на уже заданный вопрос об одном controlled update/restart и одной desktop/mobile entry-проверке. Общий продуктовый ответ о зелёном стиле и «нон стоп» не считается таким исключением.

Сохранён известный риск: если запись prepared после переключения source завершится ошибкой, новый source остаётся остановленным; автоматического rollback нет. Требуется отдельное контролируемое восстановление, не повтор всего окна. Подготовка не доказывает динамическую доставку или готовность релиза. TECHNICAL_READY/PILOT_ALLOWED/MVP=false.
