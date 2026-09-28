# Control-home: последовательность root до установки

Карточка B30-D-CONTROL-HOME-INSTALL-PREFLIGHT-REVIEW. Source-only proposal, не допуск к запуску. Root является автором этого документа, но не принимает его самостоятельно. Base 00607be24a608e481efa4437408e7b338fcafe93. Операций установки и новых probes по этому документу: 0.

## Закреплённый договор

INTERFACE.json SHA256 fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d; independent DESIGN_REVIEW_RU.md e0f12968cbc3d8f0049d186191f34c141fa31033984bbb935dde40dab3847367, ACCEPT_FOR_IMPLEMENTATION only. Owner message 01a0e6b9-460d-7340-b2f8-7ea2cbe16b4b разрешает установку/перенос рабочего состояния. Он не снимает C64 policy exception и исторические лимиты.

C source: C:/Users/user/AppData/Local/BOSDev. D target: D:/3/BOSDev/control-home. C preserved archive: C:/Users/user/AppData/Local/BOSDev.pre-D-20260928. Anchor: D:/3/BOSDev/control-home-authority.json. Private evidence: D:/3/BOSDev/evidence/bos3-control-home-install-20260928. Никакие credentials/state contents не выводятся в публичный отчёт.

## Следующая ограниченная подготовка

До установки root должен получить точные принятые core/consumer hashes и отдельный review нового focused synthetic runner. QA_SCOPE_PROPOSAL.json не разрешает выполнение. Старый полный channel suite, EOF и C64 не перезапускаются. Native junction и межпроцессный lock обязательны для технического GO; mocks не заменяют их.

После review root может подготовить операционный скрипт только в scratch с отдельными явными фазами snapshot/prepare/alias/activate/verify. В live tools этот скрипт не устанавливается. Он должен пройти независимый code review до запуска. Ни один status JSON не разрешает ему автоматически перейти к следующей фазе. Shell commands ниже описывают требуемое поведение, не выдаются за уже выполненные.

## Недостающая quiescence

Observer checkpoint 042a84a64a6cce1921c1fbc27a064a02da39c812990277b12c615b9fbc1785e1 подтверждает только отсутствие его C writes после handoff 06:41, global_quiescence_proven=false. Root не отправляет через старый ledger. Оба source-author работают только в scratch, live writes запрещены карточками. Нельзя заключить, что все другие callers остановлены, из отсутствия изменений hash или из успешного краткого захвата lock.

Известная регистрация MCP bos_control использует C tools/codex_channel.py и enabled_tools=[wait_threads,read_thread]. Изменение args в config не перезагружает старый процесс. Его разрешённые tools не пишут control state; фактическое отсутствие незавершённого write/transport нужно подтвердить отдельно. Исторические C65/C66 maps не проверяли Task Scheduler, Run keys, Startup shortcuts и процессы.

Root предлагает reviewer классифицировать только такие НОВЫЕ действия, необходимые для этой установки:

1. Read-only, bounded сопоставление существующих BoS Startup/Run/Task registrations с точными known source/setup paths. Выводить только найденные BoS identities/actions, остальные данные не сохранять. Ничего не отключать автоматически. Не менять службы, PostgreSQL, app, policy или системные задания.
2. Проверка native thread/cursor для известных владельцев, без пробуждения и записей в C ledger. Перед окном штатно поставить только heartbeat automation на PAUSED через native tool, сохранить все поля и native receipt; не править TOML. Это временное окно, а не завершение недельной цели.
3. Только если есть отдельное действующее основание: bounded read-only подтверждение отсутствия процессов control-writers/transport по known scripts. НЕ выполнять прежнюю C64 CIM/listener/runtime диагностику, не проверять порты или ресурсы, не обходить отказ загрузки того ps1 inline-командой/другим executable. Если это невозможно в текущем допуске, поставить точный blocker quiescence; отсутствующие данные не заменять утверждением об остановке.

Reviewer должен явно отделить разрешённое владельцем установочное metadata чтение от уже заблокированной дополнительной Windows-диагностики. Этот документ НЕ даёт нового разрешения на process probes. При спорном пересечении live switch остаётся запрещённым; source и независимый review продолжаются. Уже заданный владельцу вопрос не дублировать.

## Точный порядок после снятия технических gates

1. Повторно сверить срок, pinned source и отсутствие destination conflicts. Target/archive/anchor должны отсутствовать; никогда не сливать существующую папку. Проверить canonical absolute source/archive paths перед same-volume rename.
2. Сохранить freeze evidence вне home и native heartbeat PAUSED receipt. Старые in-flight transport должны завершиться, источник не должен удерживать cached writers. Не делать контрольную настоящую отправку через мигрируемый ledger.
3. Под старым существующим byte lock получить полный opaque manifest только C control-home, включая backups/tools/thread receipts. Native file identities, single-link regular files, запрещённые reparse, ACL owner/DACL, размеры и SHA256. Это не повтор storage whole-root inventory16; scope ровно один control-home, до сих пор не снимавшийся полностью. Любой неожиданный тип/ошибка останавливает шаг.
4. Создать полный D copy без удаления C и без traversal reparse. Новый постоянный D lock создаётся только establishment. Сохранить точные backups setup файлов и глобального config до allowlisted overlays. Сохранить source ACL явно, проверить права владельца и отсутствие расширения доступа к закрытым state/backup данным. Обычный Copy-Item без проверки ACL не считается достаточным.
5. PREPARED anchor не допускает tools. Все source/destination hashes должны совпасть кроме exact accepted overlays и явно нового lock identity. Snapshot mutable-state hashes фиксируют сохранность переноса, но не навечно ограничивают последующие разрешённые записи.
6. Закрыть snapshot handles при сохранённом внешнем freeze. Rename C source в точный отсутствующий C archive штатным Move-Item -LiteralPath в одном PowerShell, затем New-Item -ItemType Junction на старом C имени к exact D target. Никакого cross-volume move, recursive deletion, cmd /c deletion, force, fallback или автоматического повторения. При отказе сохранить фазу и остановиться.
7. Независимый prepared receipt включает generation, hash snapshot/overlays/backups, native C/D root/lock equality, ACL evidence, raw codes и quiescence. Только независимый ACCEPT_MIGRATION_COMMIT на точный prepared hash разрешает ACTIVE.
8. Root создаёт ACTIVE anchor через same-parent temporary file, flush/fsync и atomic replace. Runtime не умеет делать establishment. Readback фиксирует фактическую generation/phase. Uncertain result не повторять автоматически и не лечить C fallback.
9. Разрешённая installed verification: C/D/default resolver, один lock/ledger, hash сохранённых данных, coordinator read-only status. Без send, app, browser, DB, PG, startup wrapper и C64. Независимый финальный reviewer принимает CONTROL_HOME_INSTALLED в этом узком scope.
10. Точная правка MCP argv C tools -> D tools сохраняет остальные config bytes/значения; backup обязателен, Codex не перезапускается. Возобновление штатного heartbeat с прежними ID/thread/15min/cutoff и уточнением D authority только после final acceptance. Не возобновлять запрещённые callers.

Нужен отдельный exact script/command review. Этот лист не является выполненным переносом, QA PASS, приложением, полной проверкой Windows или разрешением product runtime. До ACTIVE failure оставляет PREPARED и исходные C bytes; после ACTIVE D остаётся authority, нужен отдельно проверенный forward recovery без stale-C reset.
