# Независимый design review переноса control home

Вердикт: **ACCEPT_FOR_IMPLEMENTATION**.

Дата: 2026-09-28. Карточка: B30-D-CONTROL-HOME-AUTHORITY-REVIEW. Reviewer: /root/bos3_d_migration_review. Автор контракта: /root/bos3_d_authority_design. Requested gpt-6-astra/high; observed runtime UNCONFIRMED. Проверен дизайн, а не реализация и не выполненный перенос.

## Точные входы

Все пять SHA-256 независимо вычислены чтением указанных файлов и совпали с назначением root:

| Файл | SHA-256 |
| --- | --- |
| DESIGN_REVIEW_CARD.json | 5aeb797281ab2837446e6a3c8aeb98bc53376efc70ef249698fcc17bfc19d8e1 |
| architecture/INTERFACE.json | fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d |
| architecture/CONTRACT_RU.md | 27212bbb1ec9c7c8b779705538e11cc0ff0bd9edc33d32b7a499283baa622da5 |
| SOURCE_BASES.json | 0de112a66fd94aa369f4a6e7e2fcbbdceed0289eec021432366fd3ca6674732d |
| D:/3/BOSDev/evidence/storage-d-20260928/install-request/OBSERVER_CHECKPOINT.json | 042a84a64a6cce1921c1fbc27a064a02da39c812990277b12c615b9fbc1785e1 |

Base commit во всех четырёх JSON согласован: 00607be24a608e481efa4437408e7b338fcafe93. Проверено совпадение двух source и семи consumer baseline pins с SOURCE_BASES.json. Это сравнение данных manifest; фактические байты перечисленных Python/PowerShell providers этим review не перечитывались и не принимаются.

## Findings

Конкретных ошибок корректности, требующих изменения проверенного design до реализации, не обнаружено. Запрошенные ниже доказательства уже предусмотрены контрактом и не являются новыми findings или дополнительным общим вопросом владельцу.

## Основания решения

- CONTRACT_RU.md:22, 32, 40 и INTERFACE.json:19, 50, 59 задают один физический D home, один постоянный lock и один ledger. C становится проверяемым alias; C archive запрещён как рабочий home. Нет fallback или bootstrap при пропаже authority/state.
- CONTRACT_RU.md:34, 36, 38 и INTERFACE.json:20 задают лексическую проверку до разрешения пути, типы файлов, native identity, неизменную generation и проверяемые receipt hashes. Изменяемые queue/observer/ledger не привязаны навечно к snapshot hash. Граница доверия ownership/ACL указана явно.
- CONTRACT_RU.md:42, 44, 50 различают source API и consumer import/forwarding, закрывают missing-ledger fallback и CLI AppTools ordering. Unknown legacy records и неопределённые отправки сохраняются; ошибка authority у observer не превращается в отчёт с пустыми inputs.
- CONTRACT_RU.md:58, 64 учитывают старый MCP worker, импортированные providers, незавершённые transport calls и heartbeat. Изменение регистрации и единичный lock не объявляются полной quiescence. Source-stale worker допустим только при доказанном ограничении чтением и исключении state/send операций.
- CONTRACT_RU.md:65, 66, 67, 68 требуют frozen snapshot, сохранённые исходные C bytes, backup setup, полный D copy с перечисленными overlays и независимое ACCEPT_MIGRATION_COMMIT до ACTIVE. INTERFACE.json:123 отдельно включает backup точной правки MCP argv.
- CONTRACT_RU.md:69, 70, 74, 76 задают одну точку commit authority, остановленных writers во время проверки и отдельную final acceptance перед возобновлением. Неопределённый commit не разрешает C fallback; после ACTIVE восстановление продолжает D authority.
- CONTRACT_RU.md:80, 82, 84 и INTERFACE.json:133 требуют изолированные fixtures, fake transport, source-bound review, учёт исторических попыток и физические Windows junction/lock доказательства. Mock или NOT_RUN не заменяют обязательный QA.

## Границы принятия

Принят минимальный договор реализации двух пакетов и последующего root command sheet. Нет принятия source diff, runtime file-identity API, реального launcher, QA результатов, установленного набора файлов или миграции.

До переключения root должен закрыть уже перечисленные в контракте gates:

1. Независимое review точных source/consumer diff, включая native Windows identity, импорт provider, fail-closed ошибки и install manifest.
2. Разрешённый bounded synthetic runner, история попыток, raw QA и независимый verdict. Физические junction и межпроцессный byte lock нельзя заменить mock.
3. Финальная карта callers/registrations/cache и доказанная остановка heartbeat/writers с завершением transport операций. OBSERVER_CHECKPOINT.json прямо сохраняет global_quiescence_proven=false.
4. Frozen source metadata/ACL, snapshot, backup setup/config, точный root command sheet и отсутствие конфликтующих destination objects.
5. Независимое ACCEPT_MIGRATION_COMMIT на installed bytes/generation/prepared receipt, затем readback ACTIVE и final installed receipt до разрешённого возобновления callers.

Поручение владельца на установку и перенос root уже подтвердил. Повторного общего разрешения не требуется. Отдельный C64 Windows runtime exception остаётся неизменным; этот verdict не разрешает обход блокировки другим shell/executable или запуск заблокированного route.

## Выполненные проверки

Разрешённые операции: bounded text reads, SHA-256 пяти входов, разбор четырёх JSON как данных средствами PowerShell, сравнение base/pins, проверка отсутствия собственного output перед созданием. Все относящиеся к review команды завершились с exit code 0. Полный текст обоих design файлов прочитан; усечённый хвост общего вывода перечитан отдельно.

helper/test/import/AST/parser-code executions=0; live state/secret reads=0; process/resource/policy/registration probes=0; source edits=0; copy/install/activate operations=0. JSON data validation не запускала проектный код. Создан только этот review-файл в разрешённом allowlist; commit не создавался.

TECHNICAL_READY=false; PILOT_ALLOWED=false; migration_accepted=false; CONTROL_HOME_INSTALLED не подтверждён.

Следующий разрешённый шаг: root назначает реализацию source и consumers в отдельных копиях с указанными allowlists, затем независимый review и предусмотренные QA gates. Любое изменение принятых CONTRACT_RU.md/INTERFACE.json требует сопоставления с этим verdict; он относится только к указанным выше SHA-256.
