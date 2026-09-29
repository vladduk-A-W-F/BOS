# B30-D-CONTROL-HOME-OPERATION-SOURCE: исходник установщика

Авторская подготовка пяти фаз `snapshot / prepare / alias / activate / verify` завершена для независимого source review. Это продолжение той же карточки по прямому поручению владельца 29.09.2026, не новая попытка QA и не установка. Старая копия `operation/resume-20260929` сохранена без изменений. Requested `gpt-6-sol/medium`; observed `UNCONFIRMED`.

## Исходник и границы

`install_control_home.py` реализует точные source/dependency hashes, per-phase admission и fresh quiescence refs, immutable one-shot started/failure/completion receipts, полный opaque snapshot под старым byte lock, полную D copy, backups и overlays, строго выбранный MCP argv byte span, PREPARED, C archive и junction, независимый commit acceptance на immutable final prepared receipt, ACTIVE anchor и read-only verify. Фазы вызываются только отдельно; ошибки и partial outputs сохраняются без auto retry/rollback.

`native_windows.py` реализует NTFS gate для core-compatible `GetFileInformationByHandle` identity, запрет reparse/hardlinks/ADS/EFS/compression/sparse, owner/group/DACL fingerprint/copy/readback, same-parent `MoveFileExW(...,0)` и единственный `FSCTL_SET_REPARSE_POINT` mount-point junction с GET и C/D identity readback. В исходнике нет shell `mklink` или fallback. Native ACL scope ограничен owner/group/DACL; SACL/audit/MIC и неподдерживаемые metadata не объявлены сохранёнными.

`NATIVE-FLUSH-1` исправлен в новом source: ошибочный directory `FlushFileBuffers` удалён. Для regular temp файла есть `flush`/`os.fsync` до same-parent publication/replace, затем reopened hash и ACL readback. Это не гарантия POSIX directory fsync или атомарности всей многофайловой установки; неопределённый результат требует отдельного persisted-state разбора. Независимый reviewer ещё должен подтвердить исправление на финальных байтах.

## Точные файлы

| Файл | SHA-256 |
| --- | --- |
| `install_control_home.py` | `756bf4e14e5555a5866beb9083aa01e864bb757909d747eef9afb66f202217b3` |
| `native_windows.py` | `cd1905d775f7e85f68f3151203d6407f7e73525f051595dd8b9a96ac2e220415` |
| `OPERATION_CONTRACT.json` | `26534e258d24d47237b4faf37e9c5246432e0f07e9260ea77ceec60fa76847a0` |

CARD `acc92026a4bf97f57770337601acc77877caa514f1d8dcc371483a7593c122cd`, architecture interface `fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d`, command sheet `7e8e7883ebf331a39ac37a3e6677770dbccea3b44f3171f39d9c634e74820fe5`, core manifest `00997c1323aaf7b8927f7c36ffbd341b422695402fc925012f9a8ff74e03598c`, consumer manifest `3b684264bf6c3ae1825c8bbdd2ce9bd8e28e9618d1cdd04abd900f60a3253ec9` сверены. Guidance reviewer `91b1166898ac8ee55f4494d96425e18a12cbad8212359dabeda613c9fce7b847` прочитан. Принятый static dependency review `21c32c1a7835002c55e2d14eec9bea269d29c36a02ed73a53f9b4d497868ac67` не повторялся.

## Проверки и следующий gate

Только text reads, SHA-256, JSON data parsing и редактирование allowlisted source; exit codes этих проверок `0`. Python import/AST/parser/compile/`--help`, tests/build/helper execution и live C state/config/ledger reads: `NOT_RUN`. Native ACL/copy/junction/anchor actions, process/resource/policy/registration probes, AppTools/transport и Git writes: `0`. `executions=0`; focused QA `1/1` потрачен на первом `setUp`, автоматического повтора нет; C64 не менялся.

До любого исполнения нужны отдельные точные root admission и свежие native quiescence/heartbeat/transport receipts, review source и QA, exact global config before/reviewed-after bytes и config span, независимый `ACCEPT_MIGRATION_COMMIT` после ALIASED. Текущий JSON contract не является таким admission. Следующий шаг: независимый consequential review этих конкретных файлов, затем root может интегрировать inactive source archive. `SOURCE_COMPLETE=false` до verdict; `TESTED=false`, `INSTALLED=false`, `MIGRATED=false`, `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`.
