# B30-D-CONTROL-HOME-CORE-INSTALL-SOURCE

Статус: source-only кандидат для независимого review; установка и QA не выполнялись.
Основа: canonical `00607be24a608e481efa4437408e7b338fcafe93`,
INTERFACE `fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d`,
design verdict ACCEPT_FOR_IMPLEMENTATION `e0f12968cbc3d8f0049d186191f34c141fa31033984bbb935dde40dab3847367`.

## Изменение

`bos_dev.py` сохраняет лексические константы C/D без import-time `.resolve()`.
Resolver допускает только D либо точное C имя, проверяет ACTIVE anchor и хеши
двух receipts, Windows file identity, точную junction C -> D, постоянный lock,
regular single-link state-файлы и schema. Проверка не создаёт каталогов и state.
`state_lock` открывает только существующий `.queue.lock` как `r+b`, сверяет
handle identity и повторяет authority после byte lock. `init` лишь подтверждает
полный комплект и возвращает `created=[]`.

`codex_channel.py` использует D home, проверяет home/target/self/аргументы и
существующий ledger до `AppTools` в public и CLI send, повторно проверяет ledger
под lock и не создаёт пустой журнал. `status` читает observer под тем же lock.
Target IDs, transport args, model, prompt hash и неопределённые отправки не менялись.

Новый `test-control-home-authority.py` описывает отдельное synthetic Windows
дерево, настоящий junction и два процесса на одном byte lock; ACTIVE/PREPARED,
неверные пути, missing/invalid ledger, missing lock и CLI self-refusal. Это
только исходный текст, не результат теста. Временные QA fixtures не входят в
устанавливаемые tools.

## Точные файлы

| Файл | SHA-256 |
| --- | --- |
| staged/bos_dev.py | `5dcd90483a5857fc306002f106a0274b33017049758ebe1926d852b68d099699` |
| staged/codex_channel.py | `a02012a1d826bacf7ceb9d19e0ff81fad69cb588bdbb28d1a1ed1a85f9d97040` |
| staged/test-control-home-authority.py | `ed9bc1c41f871321d7761f8075494ed851cef4312e1e2640bbb76710d5afc191` |

Native identity сериализуется как lower-case hex: volume serial 8 цифр,
file index 16 цифр из `GetFileInformationByHandle`. Acceptance receipt должен
содержать `verdict=ACCEPT_MIGRATION_COMMIT`, `generation` и
`prepared_receipt_sha256`; последнее равно digest prepared receipt в anchor.
Reviewer и root должны закрепить именно этот формат в command sheet до ACTIVE.

## Проверка и границы

Сверены входные и выходные SHA-256, source и контракт прочитаны. Исполнение,
импорт, parser/AST/compile, тесты, native junction/process, AppTools/network,
live state/ledger/home, установка и policy probes: `NOT_RUN`, `executions=0`;
exit codes для них отсутствуют. Независимый reviewer verdict по этому diff
ожидается. TECHNICAL_READY=false; PILOT_ALLOWED=false.
