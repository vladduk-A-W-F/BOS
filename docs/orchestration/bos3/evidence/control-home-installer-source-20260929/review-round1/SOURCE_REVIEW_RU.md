# Независимый consequential source review

Verdict: **CHANGES_REQUIRED**. `SOURCE_COMPLETE_STATIC_NOT_TESTED_NOT_INSTALLED` не выдан. Все пять фаз имеют реализацию, но ниже остаются конкретные correctness/safety gaps. Reviewer executions=0.

## Exact Candidate

| Файл | Независимо сверенный SHA256 |
| --- | --- |
| install_control_home.py | `756bf4e14e5555a5866beb9083aa01e864bb757909d747eef9afb66f202217b3` |
| native_windows.py | `cd1905d775f7e85f68f3151203d6407f7e73525f051595dd8b9a96ac2e220415` |
| OPERATION_CONTRACT.json | `26534e258d24d47237b4faf37e9c5246432e0f07e9260ea77ceec60fa76847a0` |
| MANIFEST.json | `b59033ab026596c7cfd284e7c2b470b801217069d2e2bb1221791335b943f617` |
| REPORT_RU.md | `e924f88cde5fc65e3d73bfa92bb6f30eb6570e8b109227087c131026b5edee09` |

Основания: CARD `acc92026a4bf97f57770337601acc77877caa514f1d8dcc371483a7593c122cd`, native guidance `91b1166898ac8ee55f4494d96425e18a12cbad8212359dabeda613c9fce7b847`, принятые INTERFACE/core/consumer contracts. Requested reviewer `gpt-6-astra/high`; observed `UNCONFIRMED`. Reviewer независим от автора и root-оператора. Полностью прочитаны два frozen Python файла, contract, manifest/report; дополнительно ограниченно прочитан ранее принятый core resolver для проверки совместимости. Никакого импорта или исполнения.

## Findings

### OPS-1 / P1: Commit не защищает полный перенесенный D tree

[activate, строка 598](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:598) перепроверяет только пять обязательных state files; перед этим проверяются overlay/config hashes. Остальные opaque backup/settings/history/thread-receipts/tools из source manifest и ACL D дерева не сравниваются с ожидаемым состоянием. [alias, строка 524](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:524) сверяет лишь D root/lock identities, а полный inventory относится только к C. [verify, строка 631](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:631) повторяет тот же ограниченный набор.

Следствие: после PREPARE удаление/изменение, например, opaque backup под D или изменение его DACL не препятствует ALIAS/ACTIVE/успешному phase verification, если пять state files и overlays сохранились. Совпадение полного C archive не доказывает сохранность D. Это особенно существенно между отдельно вызываемыми фазами. Факт live corruption не утверждается; пропуск следует из ветвей кода.

Минимальный delta: сформировать immutable expected full D manifest, основанный на source manifest, с точными разрешенными overlay deltas и новыми identities; сохранять его в prepare/final prepared receipts. До alias, ACTIVE и завершения verify сравнивать полный set paths/types/bytes/ACL/поддерживаемых attributes и native identities, исключая только документированные изменения. Проверять также security и native type для setup/config overlays/backups, не только bytes. Не подменять это новым baseline inventory, который просто узаконит уже случившееся отклонение.

### OPS-2 / P1: PREPARE может перезаписать появившийся anchor

[prepare, строка 512](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:512) публикует начальный PREPARED через `atomic_bytes`, который без проверки текущего destination делает `os.replace` на [строке 268](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:268). Отсутствие ANCHOR/C_ARCHIVE проверено только в предыдущем snapshot вызове, не в prepare. Между фазами возможен новый конфликт; fresh quiescence на actors не является проверкой generation/phase уже существующего anchor.

Следствие: существующий чужой PREPARED/ACTIVE anchor может быть заменен текущим PREPARED, вместо обязательного conflict refusal. Код позже проверяет свои draft hashes, но это уже после перезаписи.

Минимальный delta: initial PREPARED publish только в гарантированно отсутствующее имя, с native absent-destination publication без replace-existing. Повторно проверить destination/archive/anchor preconditions при входе PREPARE. Для alias/activate replacement явно требовать exact предыдущий hash/generation/phase/regular single-link identity непосредственно перед заменой. Не перезаписывать неожиданный anchor и не восстанавливать его автоматически.

### OPS-3 / P1: Snapshot lock handle не привязан к snapshot identity

[snapshot, строка 333](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:333) инспектирует lock path, но результат не сохраняет. Затем открывает `r+b` stream, захватывает byte и вызывает inventory. [inventory, строка 320](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:320) правильно читает lock bytes через owning stream, однако entry identity/ACL получены отдельным path lookup. Ни до, ни после acquisition нет сравнения GetFileInformationByHandle для `msvcrt.get_osfhandle(stream.fileno())` с проверенным lock path и root identity.

Следствие: при замене lock/root между проверкой/open/acquisition manifest может связать байты locked объекта A с identity пути B, а исключение writers обеспечивается не на том объекте. Требование не предполагает защиту от администратора, но именно обязательная повторная native identity validation отсутствует; quiescence JSON не заменяет ее. Принятый core уже выполняет handle identity recheck на [bos_dev.py:268](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/staged/bos_dev.py:268).

Минимальный delta: получить identity owning OS handle и сохранить ожидаемые root/lock identities до acquisition; проверить equality handle/path/root сразу после получения lock и после inventory до освобождения. Lock manifest entry должен привязываться к owning identity; все несоответствия закрывают фазу. Не открывать второй data handle на locked byte, не создавать новый lock и не отпускать lock для обхода отказа.

### OPS-4 / P1: VERIFY не требует доказательства совместимости с current resolver

[verify, строки 647-650](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:647) принимают coordinator receipt по четырем полям: schema, generation, active_anchor_sha256 и read_only=true. Нет обязательного outcome success, C/D/default resolver results, exact loaded provider hash или доказательства того же byte lock/ledger. Сам verify эти runtime semantics не проверяет. Snapshot на [строке 344](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:344) требует наличие файлов, но не валидность их JSON envelopes, которые обязательны для текущего core.

Следствие: существующий syntactically invalid state либо неверная config/queue/ledger schema может быть непротиворечиво скопирована и закоммичена; hash-only checks проходят, а current resolver отвергает authority. Receipt без успешных resolver результатов также проходит gate. Это source counterexample, не утверждение о live contents. Обязательные core checks находятся на [bos_dev.py:234](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/staged/bos_dev.py:234).

Минимальный delta: до ACTIVE отдельно validate обязательные JSON object/envelope invariants, совместимые с frozen core, сохраняя исходные bytes и opaque records. Для VERIFY требовать точный отдельно допущенный coordinator verification receipt с успешными C/D/default results, canonical D/root/lock/generation, pinned executed source и bounded same-lock evidence; либо реализовать эквивалентную проверку под отдельным разрешенным verification scope. Не импортировать/запускать продукт в текущем source review и не делать фальшивый successful receipt. Дополнить OPERATION_CONTRACT schema так, чтобы failed/incomplete receipt не проходил по одному read_only.

### OPS-5 / P2: Overlay baseline взят из исторического source input

[prepare, строки 498-503](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/operation/source-complete-20260929/install_control_home.py:498) использует `source/MANIFEST.inputs` как expected_before copied D tools. Там указаны bos_dev `9953e621...` и codex_channel `371a02a4...`. Это baseline разработки нового source, не hash фактического frozen C home. Последний рассмотренный административный sync связан с legacy source pins `88dd3f8d...` и `3a85a67b...`; новый live read для этого вывода не выполнялся.

Следствие: при snapshot именно уже принятого legacy состояния D copy сохранит эти bytes, но первый reviewed_overlay потребует другой исторический hash и остановится после создания D дерева. Защита от drift нужна, однако сравнение с не тем baseline делает PREPARE непригодной для объявленного исходного состояния. Та же категория касается setup baseline, который нельзя угадывать по manifest разработки.

Минимальный delta: before hash каждого D overlay брать из immutable source snapshot и связывать с separately reviewed plan/admission; для внешнего setup заранее закреплять exact approved before hashes и backup policy. Accepted after hashes остаются из frozen source/consumer manifests. Проверить все baseline и возможные конфликты до начала D copy/overlay mutation. Не ослаблять hash check и не принимать любой обнаруженный файл автоматически.

## Подтвержденные Части

- **NATIVE-FLUSH-1 закрыт**: в frozen native source нет directory FlushFileBuffers, file writes имеют flush/os.fsync, same-parent publish/replace и readback. Contract честно не обещает directory fsync или многофайловую power-loss transaction.
- Source действительно содержит пять отдельных фаз и не заменяет их unconditional missing-approval stubs. Недостающие source/QA/phase/quiescence/commit approvals проверяются как внешние документы. Это не означает, что такие approvals сейчас существуют.
- Native identity соответствует core 8/16 lowercase hex. NTFS gate, reparse/single-link и ADS checks реализованы; unsupported compression/EFS/sparse attrs отвергаются. Owner/group/DACL readback использует реальный GetSecurityInfo/SetSecurityInfo и отдельный DWORD status. NULL/absent DACL отвергается. Возможная нормализация/наследование Windows ACL может дать fail-closed отказ; native QA этого не проверяла.
- Native rename использует same-parent MoveFileExW(...,0), без cross-volume copy/delete fallback; junction использует один SET_REPARSE_POINT и GET/readback, не shell replay. Проверка alias root/lock identity предусмотрена.
- MCP config использует exact reviewed before/after bytes и span, TOML semantic comparison только одного args элемента, backup до replace. Нельзя считать generic string replacement или применение scratch ACL эквивалентным: текущая реализация пытается сохранить destination ACL.
- Post-alias final prepared receipt отделен от stage receipt, core-compatible `{path,sha256}` refs и acceptance binding реализованы, ACTIVE имеет exact 11-key schema. Нет автоматического перехода между фазами; marker/failure outputs сохраняются. Ошибка после ACTIVE не вызывает rollback/C fallback.

Это признание проверенных участков не снимает OPS-1..OPS-5. Особенно первые четыре касаются обязательных commit/lock/verification boundaries, а не оформления документации.

## Границы И Следующий Delta

Root получил findings в ходе чтения. Требуется исходный авторский repair в той же allowlist, сохранение этого frozen candidate/receipt history, обновление точных contract/manifest/report hashes и независимый delta review всех пяти closures. Никаких tests/imports/probes ради устранения findings этим отчетом не разрешается. SOURCE_COMPLETE остается false; inactive integration как принятый installer source пока не допускается.

Review ограничен статическими текстами и evidence hashes; native API основания приведены в связанном NATIVE_METHODS_REVIEW_RU.md на первичные Microsoft/Python docs. Tests/import/AST/parser/compile/help/installer/native operations/live C/config/ledger reads, process/resource/policy probes и transport: 0. Read/hash commands завершились exit 0. Изменен только этот SOURCE_REVIEW_RU.md.

QA1/1 spent, C64, остальные исторические limits и cutoff 2026-10-04T23:59:00+02:00 сохраняются. Даже будущий SOURCE_COMPLETE_STATIC_NOT_TESTED_NOT_INSTALLED не будет QA PASS, installation/cutover admission или MIGRATED. TECHNICAL_READY=false, PILOT_ALLOWED=false.
