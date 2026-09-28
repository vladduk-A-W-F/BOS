# Независимый review исправлений R1

Вердикт по product source: **ACCEPT_SOURCE_FOR_BOUNDED_QA_PREPARATION** на перечисленных exact pins. Прежние F1-F4 исправлены по статическому review. Это не QA PASS, runtime acceptance или installation acceptance.

Вердикт по consumer test admission: **CHANGES_REQUIRED_TEST_CLEANUP_GUARD**, finding R1-T1/P2 ниже. Core authority test source пригоден для подготовки отдельного bounded QA admission; исполнения не было. F5 закрыт в части подготовленного core/consumer coverage, но phase-fault operation QA остаётся отдельным обязательным gate.

Дата: 2026-09-28. Карточка B30-D-CONTROL-HOME-IMPLEMENTATION-REPAIR-REVIEW-R1. Reviewer /root/bos3_d_migration_review независим от авторов /root/bos3_channel_test_sol и /root/bos3_d_consumers. Requested gpt-6-astra/high; observed runtime UNCONFIRMED. Этот файл является единственным изменённым reviewer output.

## Оставшийся finding

**R1-T1 / P2: проверить конечный scratch target непосредственно перед recursive cleanup.**

Места: `consumers/staged/test-control-home-consumers.py:64` и `:67`; аналогично `consumers/staged/test-codex-channel.py:24` и `:100`.

Consumer suite проверяет ordinary parent при создании fixture, но перед `self.temp.cleanup()` не подтверждает resolved containment самого generated root и отсутствие reparse на его текущем пути. У обновлённого legacy suite прямой cleanup также зарегистрирован через atexit. Проверка родителя до создания каталога не является проверкой конечного удаляемого объекта перед рекурсивным удалением. В отличие от этого, authority suite уже проверяет scratch/base и дерево в `_cleanup` перед shutil.rmtree.

Минимальный ремонт только тестов: один guarded cleanup, который проверяет точный назначенный scratch parent и сам временный target по абсолютному разрешённому пути, отказывает при redirect/mismatch и сохраняет fixture при неопределённости. Для специально создаваемой file-symlink fixture удалять только сам известный leaf без traversal либо сохранять fixture; не расширять cleanup на произвольные reparse. Все teardown/atexit/finalizer маршруты должны использовать ту же границу, чтобы отказ guard не сопровождался поздним blind cleanup.

Это блокирует допуск consumer tests, а не исправленный product source. Полный legacy test-codex-channel suite и без этого не входит в разрешённое предложение запуска; правка его import/cleanup не даёт ему новый бюджет.

## Закрытие прежних findings

| Finding | Статический результат |
| --- | --- |
| F1, provider origin | CLOSED. local_flow/repo_health загружают exact D/tools bytes через checked file handle; проверяют parents/type/link count, открытый file identity и cache marker path+hash. Поиск sys.path больше не выбирает fallback. bos_flow отдельно загружает exact setup/local_flow, затем provider/channel через этот loader. |
| F2, live test imports/factory | CLOSED для прежней причины. Новый consumer suite создаёт scratch copies, заменяет только уникальные path literals, привязывает exact modules и передаёт explicit forbidden/fake transport factory. Неверный ранний отказ больше не ведёт к production home по default. Cleanup admission отдельно R1-T1. |
| F3, unrelated opaque ledger | CLOSED. required_ledger проверяет envelope; prior_delivery валидирует выбранный ID и возможные относящиеся к отправке records. ACKNOWLEDGED возврат не блокируется чужой opaque записью. UNCONFIRMED/SENDING и известный duplicate не становятся разрешением повторной отправки. |
| F4, authority failure -> report | CLOSED. Core нормализует рассмотренные receipt/stat/resolve/open/lock ошибки в ControlHomeError; repo_health больше не переводит locked_inputs failures в пустые inputs. Подготовлен second-stage refusal/no-output test. |
| F5, coverage | CORE_CONSUMER_SOURCE_GAPS_ADDRESSED, NOT_RUN. Добавлены SUSPENDED/receipt, native replacement/reparse/hardlink, acquisition generation, transferred ledger, exact provider origin/cache/fallback и output ordering checks. PHASE_FAULT_OPERATION_QA_PENDING остаётся отдельным gate. |

Новых product-code regressions в actual R1 diff не обнаружено. Не переоценивались неизменные approved design bytes и неизменные wrappers. Native Win32/CRT поведение loader/identity/byte lock пока подтверждено только чтением исходника; его ещё должен проверить разрешённый Windows QA.

## Исправление ошибочного test SHA

Независимое чтение actual authority test даёт `e150232e750b7e1af28861981eaaaf47dc25b147820a62741cc9852f2920dfe5` (64 hex). В сохранённых авторских manifest/report был `e150232e750b7e1af28861981eaaf47dc25b147820a62741cc9852f2920dfe5` (63 символа, пропущено одно `a`).

Текстовое сравнение сохранённого и текущего manifest обнаружило только исправление этой одной строки; сравнение reports обнаружило только соответствующую строку таблицы. Текущее значение совпадает с независимо вычисленным hash source file. Это коррекция evidence pointer; сама по себе она не является тестом или дополнительным принятием кода. Reviewer не менял ни pointer, ни source.

| Сохранённый/текущий evidence | SHA-256 |
| --- | --- |
| source/MANIFEST_R1_BEFORE_HASH_CORRECTION.json | ecd0004637df60aa420fbe60ba2c7eecb82e2f387dfbee5a4b6958b7c87e3880 |
| source/REPORT_R1_BEFORE_HASH_CORRECTION_RU.md | 5133f2a48589d5807b99f4064e32052be626cc6e6928096443fe5fcdfca6bc9c |
| source/REPORT_RU.md | 758c0680576ad221c9bf4d465f72fcb6f85d9163263b4671e71c7106dfbfc3a8 |

## Проверенные pins

- REPAIR_REVIEW_CARD.json: `1b6bdd4506dc07a5172eb7701d49f644524a5f67ed78cd1820db41ce7debb19e`.
- source/MANIFEST.json: `b29c8a28afb6f592c9ba520bc4efa39fe946212627e9da51ef18f87ca0ea7ee0`.
- consumers/MANIFEST.json: `04f6db2473aa8976f4a5a19db1ea9c9675bffd971039e2b6fa96400439f94031`.
- Предыдущий IMPLEMENTATION_REVIEW_RU.md: `653245012090042f9a30890486b41b49248d33fc3ba0e571df86f80ec511e56e`, неизменён.
- Сохранённые round1 manifests: source `2071d287f61ce243730ca6fa75182ddbd877ec9707ba3b541144fd3ef94385d8`, consumers `3e17f22d8e32cea8ff102995aabb1b6f5017baf528b00c857caab992aef3a5a3`, совпали с первой приёмкой входов.

Все 11 текущих outputs и все 11 сохранённых review-round1 outputs независимо хешированы: 22/22 совпадения с соответствующими manifests. Изменённые R1 pins:

| Файл | SHA-256 |
| --- | --- |
| source/staged/bos_dev.py | 5baafc5d84a6fbc65ce65602206b27af44e17143b85affb3aeca3683e09d0b44 |
| source/staged/codex_channel.py | 40c87c417ac0a7e56725472b471bb6003f850dc8ad3873b1732cff16d6e3c02a |
| source/staged/test-control-home-authority.py | e150232e750b7e1af28861981eaaaf47dc25b147820a62741cc9852f2920dfe5 |
| consumers/staged/bos_flow.py | 0687da0606dc86431e1c034fcfddc03970bd2c716e6523ab5834581372aba274 |
| consumers/staged/local_flow.py | d4185d4f885cf9060b34775b2cc96bf662a4b0857ea7319326f14026ea522853 |
| consumers/staged/repo_health.py | cb4f52a6a7827ddee0dd59bc4e567324356717d8e8935f76b4628e7e6ad2d5c8 |
| consumers/staged/test-codex-channel.py | 62a799faa6bb349577d2d53f788eb28e00281b01b53938a63881b6786cf41a66 |
| consumers/staged/test-control-home-consumers.py | eaa21b27a5529105c1454120397c3bf3d65ae06e1b517fcdd0013568fa7e32fd |

Три wrapper outputs сохранили прежние reviewed hashes. Consumer manifest честно оставляет PENDING_ACCEPTED_CORE_PINS; REPAIR_REVIEW_CARD связывает exact core для этого review. Root может теперь отдельно зафиксировать принятое source binding, не выдавая его за live installation.

## Кандидаты bounded QA

В authority suite подготовлено 16 методов. Для exact последующего предложения могут использоваться все методы AuthorityTests из pinned файла, с сохранением классификации:

- NEW authority/native coverage: active alias identity; missing/PREPARED/SUSPENDED/invalid anchor; receipt absence/tamper/cross-drive/binding; lexical refusal; missing/invalid ledger under authority; init без recreation; replaced lock; acquisition-time generation; hardlink/reparse; two-process byte lock.
- Transition-specific, с учётом прежних SAME-PROBLEM counters: transferred ACKNOWLEDGED/UNCONFIRMED/SENDING plus opaque record; incomplete relevant-record refusal; CLI self-before-transport. Новый suite ID не обнуляет старую историю channel/target/fixture проблем.

В consumer suite подготовлено 10 методов ConsumerAuthorityTests. После закрытия R1-T1 они могут стать кандидатами: exact scratch origin, missing provider/channel fallback refusal, foreign cached provider, hardlink/reparse provider, second authority failure/no output, explicit fake-transport ordering, selected-home output refusal и source wrapper forwarding. Source string checks wrappers не доказывают PowerShell runtime behavior.

Authority и consumer suites должны идти в отдельных interpreter processes либо получить отдельно reviewed module isolation. Authority module заранее кладёт bos_dev/channel в sys.modules; consumer loader правильно отвергает такой чужой cache. Единый discovery/import обеих suites в одном процессе не является принятым способом исполнения.

`test_reparse_provider_refused_when_fixture_available` способен SKIP при недоступной file-symlink fixture. Такой SKIP должен оставаться видимым и не считаться выполненным provider-reparse QA; root сопоставляет обязательство с другими фактическими native evidence, не с total OK. Phase-fault operation tests, live quiescence и точные runner/timeout/attempt receipts ещё отсутствуют в этом review.

## Ограничения и следующий шаг

Выполнены только reads, SHA-256, text diff и JSON-data parsing. Hash/read/data checks: exit 0. git diff --no-index: ожидаемый exit 1 при изменениях. Первый rg inventory дополнительно получил os error 2 для лишнего guessed root-level review-round1; точные source/review-round1 и consumers/review-round1 найдены тем же inventory и затем проверены. Этот path lookup не был выполнением проектного кода.

helper/test/import/parser/compile executions=0; live state/secret reads=0; probes=0; transport=0; install=0. Reviewer не изменял source, manifests, reports авторов или operation/. Коммит не создавался.

Следующий шаг root: узкая правка R1-T1 прежним consumer автором и independent review изменённого guard; параллельно можно готовить exact bounded QA admission принятого product source и отдельное operation phase coverage. Исполнение этот verdict не разрешает. C64 policy exception и исторические caps неизменны; TECHNICAL_READY=false; PILOT_ALLOWED=false; migration_accepted=false.
