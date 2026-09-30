# B30-D-CONTROL-HOME-CORE-INSTALL-SOURCE

Статус: source-only ремонт после независимого CHANGES_REQUIRED; повторный review ожидается. Установка и QA не выполнялись.
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
| staged/bos_dev.py | `5baafc5d84a6fbc65ce65602206b27af44e17143b85affb3aeca3683e09d0b44` |
| staged/codex_channel.py | `40c87c417ac0a7e56725472b471bb6003f850dc8ad3873b1732cff16d6e3c02a` |
| staged/test-control-home-authority.py | `e150232e750b7e1af28861981eaaf47dc25b147820a62741cc9852f2920dfe5` |

## Ремонт после review

Исходный независимый review `653245012090042f9a30890486b41b49248d33fc3ba0e571df86f80ec511e56e`,
repair card `ae9acd25794a5f53db3d17f03964f29aa9b71f1454d19a11616d888cd25275ae`.
Reviewed originals в `source/review-round1` не менялись.

- F3: envelope ledger проверяется отдельно. Для того же ID и возможных
  совпадений target/hash остаётся fail-closed отказ; посторонняя opaque запись
  не блокирует ACKNOWLEDGED suppression и не переинтерпретируется.
- F4: cross-drive receipt и ошибки чтения, stat, junction resolve, открытия,
  timeout и освобождения lock нормализованы в `ControlHomeError`.
- F5: тестовый исходник теперь описывает SUSPENDED, missing/tampered receipts,
  hardlink/reparse, replacement lock, post-acquisition generation change,
  transferred ACKNOWLEDGED/UNCONFIRMED/SENDING рядом с opaque legacy record.
  QA-каталог закреплён внутри scratch; cleanup отказывает при неожиданном
  reparse; child загружает exact staged provider с `-B`.

Fault injection фаз до/после ACTIVE остаётся отдельным operation QA gate.
Этот core пакет не содержит installer и не заявляет полного migration coverage.

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
