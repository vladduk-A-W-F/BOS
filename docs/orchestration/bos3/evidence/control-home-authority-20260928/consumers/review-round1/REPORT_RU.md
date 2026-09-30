# B30-D-CONTROL-HOME-CONSUMER-INSTALL-SOURCE

Статус: исходники подготовлены в выделенной копии; обязательные binding core и независимое review ещё не получены. Установка, запуск и приёмка миграции не выполнялись.

## Входы и изменение

Семь исходных файлов прочитаны и сверены по SHA-256 с `SOURCE_BASES.json` и карточкой. `bos_flow.py`, три wrapper и `test-codex-channel.py` взяты из принятых staged-источников commit `00607be24a608e481efa4437408e7b338fcafe93`. `local_flow.py` и `repo_health.py` взяты из закреплённых live setup-файлов без их изменения. Точные входные и результирующие SHA-256 записаны в `MANIFEST.json`.

- `bos_flow.py` сохраняет импорт `local_flow` из setup, но `bos_dev` и `codex_channel` выбирает через фиксированный `D:/3/BOSDev/control-home/tools`. CLI проверяет authority до чтения policy/index; остальные точки `refresh` и `handoff` также используют общий resolver.
- `local_flow.py` и `repo_health.py` импортируют provider только из фиксированного D tools, вызывают resolver до state/snapshot/Git/output-эффектов и далее используют один D lock. `repo_health.collect` не переводит ошибку authority в пустые входы и `INCOMPLETE`-отчёт.
- `bos.ps1`, `bos-flow.ps1`, `start-workday.ps1` по умолчанию передают D home; явно выбранный C alias передают без подмены resolver. Coordinator path закреплён на D. Сохранён `finally` cleanup `PGPASSWORD` и исправление конфликта PowerShell `$Home`. `start-workday` записывает startup evidence только после подтверждённого coordinator status: отказ authority не создаёт output-файл; при последующем PG/app failure прежняя ветка evidence остаётся.
- Существующий channel test привязан к `source/staged` и создаёт synthetic ledger; добавлен отдельный источник четырёх consumer ordering checks. Это подготовка тестов, не результат выполнения. Исторический receiver event `00607` не тронут.

## Проверка и ограничения

Разрешены были только чтение закреплённых исходников, SHA-256 и текстовая проверка. Exit code 0 для чтения/hash команд. `MANIFEST.json` содержит результат восьми файлов. Helper/test/import/AST/parser/compile/`--help`/live state/network/AppTools/process/resource/policy/install выполнялись **0** раз; тесты **NOT_RUN**. Указанные тесты сами по себе не подтверждают физический Windows junction/lock.

До разрешённого bounded QA root должен заменить `provider_binding` на точные SHA принятых `source/staged/bos_dev.py` и `codex_channel.py`, сверить интегрированный diff и получить независимое review. Исторический полный channel suite автоматически не повторять; только согласованный адресный набор с учётом лимитов. Дальнейший cutover и состояние ACTIVE принадлежат root и отдельным gates контракта.

Известный сдвиг output при отказе coordinator status в `start-workday`: startup evidence не записывается, так как источник отказа может быть authority; stdout с неуспешным status остаётся. При status success и поздней ошибке поведение evidence сохранено.

`TECHNICAL_READY=false`; `PILOT_ALLOWED=false`; installation и migration acceptance не подтверждены.
