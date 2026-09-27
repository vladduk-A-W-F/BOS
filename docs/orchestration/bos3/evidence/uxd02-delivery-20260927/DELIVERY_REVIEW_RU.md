# UXD02: фактическая доставка dev.7

27.09.2026. Единственный исполнитель: root. Независимый reviewer: `/root/start_overview_review`.

Вердикт: **ACCEPT_SCOPED_DEV7_OWNER_LOCAL_DELIVERY_WITH_EVIDENCE_LIMITATION**.

## Точная версия

- Product: `d346f63c5ff5ea0e9d4da7a947b8788c25101c0e`, 0.3.0-dev.7.
- Immutable source/runtime: `d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`.
- Предыдущий runtime: `8114097b3ddf2c31b709ed945bfb514c404ce4f1`, dev.6.
- Manifest: `DRILLDOWN_DEV7_CANDIDATE.json`, SHA256 `823761cbc532b5707e3d3fa990be9c8aba8bcdafdcfbdbc6779d4ce18dc64509`.
- Final-pin review: ACCEPTED_FOR_ONE_SCOPED_OWNER_LOCAL_DELIVERY. Изменения runner относительно принятого шаблона ограничены exact pin/manifest/14-file allowlist.

## Один запуск доставки

| Этап | Фактический результат |
| --- | --- |
| capture | exit 0 |
| official stop | exit 0 |
| apply | exit 0, exact source d8e121a |
| official start | строка ready; native exit UNCONFIRMED_WRAPPER_WAIT |
| post-start | exit 0; один HTTP 200; exact normalized HTML |

Это не пять фаз с exit 0. Все stdout/stderr и полученные exit-файлы сохранены в `run1/`; отсутствующий start.exit не подменён нулём.

Внешний root wrapper использовал `Start-Process -Wait`, ожидающий всё дерево, включая штатный долгоживущий сервер. Сам официальный launcher записал ready и вернулся. Matching PowerShell 7.6.5 JobProcessCollection использует completion port без kill-on-close: https://github.com/PowerShell/PowerShell/blob/v7.6.5/src/Microsoft.PowerShell.Commands.Management/commands/management/JobProcessCollection.cs .

После отдельного ACCEPT_CONDITIONAL_RECOVERY завершён только wrapper 47748 через identity-checked `Process.Kill(false)`. Сервер PID50544 сохранил identity и listener, повторного start/stop не было. Первая защита отказала до действия: CIM округлил timestamp до микросекунд, тогда как receipt и .NET совпали точно в 100ns. Ошибка и исправленный guard сохранены, а не скрыты. Recovery tool exit 0 отражён в `RECOVERY_TOOL_RECEIPT.json` как транскрипция фактического результата инструмента; это не native exit official start. Убитый outer exec завершился с -1. `wrapper_exit_code:null` в raw сохранён.

## Доказательства результата

- Единственный post-start: raw SHA256 `099d9d4b22a943e5544bd1afd9cf3e9f0fa317af0e276b80e8bfa0030bcf8983`.
- Источник и prepared digest: `fd655bd44b23f5a7543cafffb39ede7c26702069ebb6a76e5784064cbc6f6c91`.
- HTML: `925c11ed621a2a62567199c6fa526b18364ce8c863a4706c6779ecb808eb5417`, совпадение после единственной подстановки версии и нормализации CRLF/LF.
- Protected aggregate до и после: `dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1`.
- PID50544, creation ticks134350072625854836, loopback127.0.0.1:8030. Runtime checkout чистый, detached на d8e121a.

База, media, пароль и прогресс сохранены по protected aggregate. Init/seed/migrate/reset, browser/JS/login, уроки, ERP/CRM-записи не выполнялись. Это не подтверждение сохранения нового учебного шага и не перенос dev.3 browser proof на dev.7. TECHNICAL_READY/PILOT_ALLOWED/MVP остаются false.

Reviewer проверил реальные файлы, pins, hash, границу wrapper recovery и post-start. Его P2 по отсутствию отдельного recovery exit artifact закрыт честным metadata receipt; исходное ограничение official start exit остаётся. Следующий шаг: оставить dev.7 работающей и двигать отдельную B30-INVOICE-CURRENCY только после подтверждённого handoff, без повторения доставки.
