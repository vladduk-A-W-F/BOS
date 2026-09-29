# Независимый delta review исходника установщика, R2

Вердикт: **CHANGES_REQUIRED**. `SOURCE_COMPLETE=false`, `TESTED=false`, `INSTALLED=false`, `MIGRATED=false`. Это продолжение `B30-D-CONTROL-HOME-OPERATION-SOURCE`, а не новая попытка QA, диагностики или установки. Requested `gpt-6-astra/high`; observed `UNCONFIRMED`. Reviewer независим от автора. `executions=0`.

## Остаточные findings

### OPS-1, P2: внешний after-state не проходит повторное исключение ADS

`install_control_home.py:566-572`, функция `verify_target`: external setup overlays и global config проверяются по regular single-link identity, owner/group/DACL fingerprint, attributes и хешу основного потока. Здесь отсутствует `native.require_single_stream(path)`. Для D дерева этот контроль есть в `inventory` (`:339`), для backup он есть внутри `fixed_ref` -> `exact_file` (`:99`), для external before-state он есть в `_external_before` (`:426`). Но начальная проверка before-state не доказывает отсутствие дополнительных потоков у опубликованного after-state и в последующих фазах.

Конкретный пропуск: после prepare у внешнего setup/config файла появился named stream; основной поток, file ID, ACL и проверяемые attributes остались прежними. `verify_target` не проверяет ни список потоков, ни время изменения внешнего файла, поэтому эта запрещённая контрактом разновидность drift может пройти проверки перед alias, ACTIVE и verify. Это не утверждение о фактическом drift: live файлы не читались.

Минимальный repair: в общем цикле after-state `verify_target` вызвать `native.require_single_stream(path)` для каждого overlay/config объекта перед успешным завершением проверки. Сохранить текущие type/identity/ACL/attributes/hash и backup checks. Новый baseline, изменение архитектуры или запуск не нужны.

### OPS-4, P2: новый validator отклоняет допустимый core UTF-8 BOM

`install_control_home.py:355-357` направляет существующие state bytes в общий receipt parser `parse_json`; тот на `:91` декодирует `utf-8`, оставляя BOM перед JSON. Принятый frozen core `source/staged/bos_dev.py:150-157` читает эти же обязательные файлы через `encoding="utf-8-sig"`; envelope predicates на `:234-243` соответствуют добавленным predicates установщика. Следовательно, корректный state object с UTF-8 BOM допустим для core, но новый snapshot validator откажет до формирования snapshot receipt. Вызовы validator также добавлены в prepare и activate.

Это несовместимость именно нового пути OPS-4 с требованием repair card «as frozen core does», а не доказательство наличия BOM в рабочем состоянии. Не следует исправлять её нормализацией или перезаписью opaque state.

Минимальный repair: отдельный state decoding path с `utf-8-sig` и обязательным object/envelope check; существующий строгий parser собственных receipts/plan/anchor можно оставить без изменений. Byte snapshot/copy/hash должны по-прежнему сохранять исходный BOM и остальные байты. Ужесточение duplicate-key policy не является предметом этого finding и может остаться fail-closed.

## Таблица закрытия

| Finding | Статическое закрытие R2 | Основание |
| --- | --- | --- |
| OPS-1 | Частично, остаток выше | `expected_target` (:519-557) выводит полное ожидаемое D дерево из frozen C manifest и трёх принятых D overlay deltas, проверяя paths/types/content/ACL/attributes, сохраняя новую D identity. `verify_target` сверяет immutable tree и external/backup identity/security/bytes перед alias (:713), ACTIVE (:768) и verify (:818). Остался external after-state ADS gate. |
| OPS-2 | CLOSED_STATIC | Prepare entry повторяет отсутствие D/archive/anchor (:667); начальный PREPARED использует `exclusive_bytes` с no-replace publication (:694-696). `replace_known_anchor` проверяет prior hash, generation, phase и native identity непосредственно перед последующими заменами (:281-300). Unexpected anchor не становится новым baseline. |
| OPS-3 | CLOSED_STATIC | Snapshot привязывает pre-open path/root identities к `msvcrt.get_osfhandle` и новому `native.identity_handle`, повторяет проверки после lock acquisition и после inventory (:372-398). Locked bytes по-прежнему читает owning stream. Native delta ограничена handle identity helper. |
| OPS-4 | Частично, остаток выше | Новые envelope predicates проверяют четыре обязательных объекта; coordinator gate (:842-873) требует PASS, exact executed core/channel pins, ACTIVE anchor/generation, C/D/default home/root/lock results, pinned successful two-process lock и same-ledger evidence. Остался state decoding mismatch. |
| OPS-5 | CLOSED_STATIC | D overlay before metadata приходит из reviewed plan и сравнивается с frozen snapshot, external setup/config baseline включает approved hash/identity/ACL/attributes. `preflight_overlays` (:429-453) вызывается до `copy_home` (:673-674); historical implementation inputs больше не используются как live before hashes. |

## Проверенные входы

SHA-256 независимо сверены: assignment, repair card, прежний review и все пять frozen candidate files совпали, 8/8. Manifest и report ссылаются на эти же три source/contract hashes. Сопоставлен actual delta с сохранённым `review-round1`; прежний review не изменён. Bounded compatibility read frozen core использован только для нового state-validator, повторной модельной приёмки неизменённых зависимостей не было.

| Вход | SHA-256 |
| --- | --- |
| `ROOT_REPAIR_REVIEW_ASSIGNMENT.json` | `be8c9fc08be68f97b7d1c5ea3a8d42160c96831f83aae73603d1645701a051c9` |
| `ROOT_REPAIR_CARD.json` | `bcdeb1d292a825d4720b0bf26d2d0811be7c973c285d13c29cf7176817b05dc3` |
| `SOURCE_REVIEW_RU.md` | `5f14fb6d6bafeb430a0b74ad8778559b55881f74b9d7a39a57176109633991c0` |
| `install_control_home.py` | `ed8a074bbfa887e8f5dd71c053bc5bf8618d989f997a3029dc7c9813430e27b1` |
| `native_windows.py` | `743836205bb0f00e592f6c2a6c26a8c242370213cfb16ec3bdd8581fe8d71add` |
| `OPERATION_CONTRACT.json` | `4bbf9d32b698a7a426b9955f5f370eac7021a48520608c6bd7245e0dfb3929ff` |
| `MANIFEST.json` | `1a1012df6ba36ad6391fc78af3b35acc6f9328e9b8f76b50bbd82f62390eab93` |
| `REPORT_RU.md` | `c333c7db263eb77f7227c179d5d6571495d21d10585ef7a67c40ff8cfa08d142` |

## Границы результата

Сохранена прежняя приёмка неизменённых частей, включая закрытый NATIVE-FLUSH-1 и core/consumer dependency review `21c32c1a7835002c55e2d14eec9bea269d29c36a02ed73a53f9b4d497868ac67`. Новые expected-tree checks не заменяют native execution evidence, а успешные receipt fields не являются выданным здесь разрешением на их получение. Не проверялись действующие state/config/ledger, процессы, политика, registration или quiescence.

Проведены только source/JSON-text reads, static diffs и SHA-256. Imports, AST/parser/compile/help, tests, installer/helper/native execution, probes, live C actions, copy/activate/transport: `NOT_RUN`, `executions=0`. QA `1/1` по-прежнему потрачен; C64, cutoff и остальные caps не изменены. Авторские файлы, root card и прежние отчёты не менялись.

Следующий допустимый шаг: авторский source-only repair двух остатков в рамках OPS-1/OPS-4, обновление pins и независимый узкий delta review. До него исходник не принят как SOURCE_COMPLETE. Даже последующая source acceptance не будет означать TESTED, INSTALLED, MIGRATED, TECHNICAL_READY или PILOT_ALLOWED.
