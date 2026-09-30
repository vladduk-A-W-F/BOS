# B30-D-CONTROL-HOME-CONSUMER-INSTALL-SOURCE

Статус: `REPAIR_R1_SOURCE_PREPARED_PENDING_INDEPENDENT_REVIEW`. Исходный пакет сохранён в `consumers/review-round1`. Исправлены F1/F2/F4/F5 из `IMPLEMENTATION_REVIEW_RU.md` SHA-256 `653245012090042f9a30890486b41b49248d33fc3ba0e571df86f80ec511e56e`; закрытие findings требует независимой проверки. Установка, запуск и приёмка миграции не выполнялись.

## Входы и изменение

Семь исходных файлов прочитаны и сверены по SHA-256 с `SOURCE_BASES.json` и карточкой. `bos_flow.py`, три wrapper и `test-codex-channel.py` взяты из принятых staged-источников commit `00607be24a608e481efa4437408e7b338fcafe93`. `local_flow.py` и `repo_health.py` взяты из закреплённых live setup-файлов без их изменения. Точные входные и результирующие SHA-256 записаны в `MANIFEST.json`.

- `bos_flow.py` читает exact setup `local_flow.py` через проверенный Windows handle; он продолжает использовать существующий setup flow, затем берёт `bos_dev` и `codex_channel` только из фиксированного D tools через его loader. Обычный import search и чужой `sys.modules` для этих модулей не принимаются. CLI проверяет authority до чтения policy/index; `refresh` и `handoff` также используют общий resolver.
- `local_flow.py` и `repo_health.py` открывают fixed D provider с native no-follow flag, проверяют родителей, тип, hardlink count и fstat identity до исполнения считанных bytes. Они вызывают resolver до state/snapshot/Git/output-эффектов и далее используют один D lock. `repo_health.collect` больше не деградирует никакую ошибку второго resolver/lock/local-input этапа до пустых входов и отчёта.
- `bos.ps1`, `bos-flow.ps1`, `start-workday.ps1` по умолчанию передают D home; явно выбранный C alias передают без подмены resolver. Coordinator path закреплён на D. Сохранён `finally` cleanup `PGPASSWORD` и исправление конфликта PowerShell `$Home`. `start-workday` записывает startup evidence только после подтверждённого coordinator status: отказ authority не создаёт output-файл; при последующем PG/app failure прежняя ветка evidence остаётся.
- Оба test source до импорта делают deterministic scratch copies core/provider и channel; пять core path literals и consumer root/home literals заменяются только с count=1, исходный и результирующий SHA вычисляются отдельно. Новый focused consumer suite готовит origin/cache/missing/hardlink/reparse, второй authority этап, output refusal и wrapper home forwarding. Windows symlink fixture даёт явный SKIP, если её создание недоступно, не PASS. `refresh` получает явный fake factory и patched state-lock refusal. Это подготовка тестов, не результат выполнения. Исторический receiver event `00607` не тронут.

## Проверка и ограничения

Разрешены были только чтение закреплённых исходников, SHA-256 и текстовая проверка. Exit code 0 для чтения/hash команд. `MANIFEST.json` содержит результат восьми файлов. Helper/test/import/AST/parser/compile/`--help`/live state/network/AppTools/process/resource/policy/install выполнялись **0** раз; тесты **NOT_RUN**. Указанные тесты сами по себе не подтверждают физический Windows junction/lock.

До разрешённого bounded QA root должен заменить `provider_binding` на точные SHA принятых `source/staged/bos_dev.py` и `codex_channel.py`, сверить интегрированный diff и получить независимое review нового repair. Исторический полный channel suite автоматически не повторять; только согласованный адресный набор с учётом лимитов. Phase-fault и физические Windows junction/two-process lock проверки остаются отдельными gates, не PASS этого пакета. Дальнейший cutover и состояние ACTIVE принадлежат root.

Известный сдвиг output при отказе coordinator status в `start-workday`: startup evidence не записывается, так как источник отказа может быть authority; stdout с неуспешным status остаётся. При status success и поздней ошибке поведение evidence сохранено.

`TECHNICAL_READY=false`; `PILOT_ALLOWED=false`; installation и migration acceptance не подтверждены.
