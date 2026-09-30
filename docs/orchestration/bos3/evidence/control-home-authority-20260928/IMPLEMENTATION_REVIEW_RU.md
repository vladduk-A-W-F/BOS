# Независимый review реализации control home

Вердикт: **CHANGES_REQUIRED**. Код не принят; подготовленные тесты не допущены к выполнению. Ниже пять конкретных findings с минимальными исправлениями. Проектный код, tests, imports, parsers и compile не запускались.

Дата: 2026-09-28. Карточка B30-D-CONTROL-HOME-IMPLEMENTATION-REVIEW. Reviewer /root/bos3_d_migration_review независим от авторов /root/bos3_channel_test_sol и /root/bos3_d_consumers. Requested gpt-6-astra/high; observed runtime UNCONFIRMED. Это одна continuation прежней карточки после fresh core FINAL_ANSWER, не новый review ID и не обход первоначального agent-thread-limit отказа.

## Findings

### F1 / P1: фиксированный provider path не закрепляет источник import

Места: `consumers/staged/bos_flow.py:15`, `:17`, `:18`, `:19`; `consumers/staged/local_flow.py:17`; `consumers/staged/repo_health.py:18`. Проверенные consumer pins приведены ниже.

`sys.path.insert(0, D/tools)` с обычным `import` лишь меняет приоритет поиска. Если нужного файла в D/tools нет, Python продолжит поиск в setup/остальном sys.path; уже закэшированный одноимённый модуль вообще обходится без поиска. Так при неполной установке или старом provider можно получить resolver/lock из иной копии и выполнить его код до проверки нового authority. Строка TOOLS с ожидаемым значением не доказывает origin. Кроме того, эта загрузка не проверяет reparse/hardlink самого tools/provider path; `_authority` проверяет state и lock, но не загружаемые tools.

Это расходится с CONTRACT_RU.md:36, 50, 54 и INTERFACE.json:97: один D provider, без setup shadowing и автоматического принятия старых copies. Минимальное исправление: fail-closed загрузка точного provider/channel файла из фиксированного tools, проверка происхождения уже загруженного модуля или отказ от него, проверка требуемых типов/containment до исполнения загружаемого файла. local_flow продолжает приходить из setup. Отсутствующий D provider, подставленный setup provider и чужой sys.modules должны проверяться изолированными тестами; нельзя лечить missing provider fallback на C/setup.

### F2 / P1: новый consumer suite может импортировать live channel

Места: `consumers/staged/test-control-home-consumers.py:11`, `:12`, `:22`, `:25`, `:54`; связанный `consumers/staged/bos_flow.py:15`, `:19`, `:85`.

Тест заранее импортирует scratch bos_dev, но не scratch codex_channel. При `staged_module('bos_flow')` сам bos_flow ставит live D/tools и D/setup перед scratch и выполняет `import codex_channel`. Поэтому при наличии файла там тест загрузит live/unreviewed channel ещё до первого test method; fallback может также выбрать иную копию. Текущий тест provider проверяет только константу TOOLS и этого не обнаружит.

Есть и конкретный пробел fake transport: patch `bos_flow.channel.AppTools` в строке 56 не заменяет default `client_factory=channel.AppTools`, захваченный при определении refresh. Пока mocked resolver выбрасывает исключение, этот путь не достигается; при регрессии проверяемого раннего отказа тест не гарантирует отсутствие реального transport. Используемые home/root также остаются реальными литералами, а core constants не переназначены в scratch.

Минимальное исправление: до импорта consumers привязать обе exact scratch зависимости, проверять их фактический origin, исключить live import search; заранее заменить все используемые пути синтетическими и заблокировать внешние I/O/subprocess маршруты. Передавать явный fake `client_factory` там, где API захватывает default. Отрицательный тест должен оставаться изолированным и при регрессии проверяемой строки. Никакого production test bypass.

### F3 / P2: неизвестная посторонняя legacy запись блокирует весь ledger

Место: `source/staged/codex_channel.py:205` (цикл required_ledger); вызов до AppTools в строке 297; prior_delivery в строках 184-194.

Новый цикл требует target/sha256/status у каждой записи. Например, журнал с корректным ACKNOWLEDGED для запрашиваемого ID и отдельной opaque legacy записью теперь отвергается целиком до duplicate suppression. Ранее этот ACKNOWLEDGED возвращался до обхода остальных records. CONTRACT_RU.md:42 требует сохранять unknown legacy records без переинтерпретации и валидировать критичные поля реально используемой записи.

Минимальное исправление: отделить проверку envelope schema/messages от валидации используемой записи и безопасной проверки возможного duplicate. Не удалять/нормализовать чужие opaque records и не ослаблять отказ для того же ID или относящегося к отправке неопределённого record. Добавить synthetic transferred ledger с ACKNOWLEDGED/UNCONFIRMED/SENDING и посторонней legacy записью, проверяя сохранение её байтов/значения и отсутствие transport при suppression/refusal.

### F4 / P2: часть authority failures превращается в degraded health report

Места: `source/staged/bos_dev.py:163`, `:169`, `:242`; `consumers/staged/repo_health.py:329`, `:332`, `:333`, `:445`.

`ntpath.commonpath` выдаёт ValueError для reference на другом drive вместо ControlHomeError. Отдельные чтения receipt и открытие lock также могут выпустить сырой OSError. В repo_health первый resolve выполняется до try, но затем locked_inputs снова проверяет authority внутри try, который ловит ValueError/OSError и подставляет пустые config/observer/index. Если между этими проверками authority/receipt/lock становится недоступным либо receipt path повреждается, ошибка второго resolve/lock может стать INCOMPLETE report с последующими mkdir/write. Это именно запрещённое контрактом преобразование authority failure в пустые inputs.

Минимальное исправление: все ошибки authority/path/receipt/lock boundary нормализовать в ControlHomeError и/или вынести resolver/lock acquisition из деградирующего catch. Ошибки обычных report inputs можно обрабатывать отдельно. Добавить изолированную проверку отказа на втором authority/lock этапе после успешного первого resolve и assert отсутствия report mkdir/write; cross-drive receipt должен возвращать заявленный ControlHomeError.

### F5 / P2: подготовленное покрытие не закрывает обязательные migration gates

Места: `source/staged/test-control-home-authority.py:77` до конца файла; `consumers/staged/test-control-home-consumers.py:28` до конца; `QA_SCOPE_PROPOSAL.json:11`, `:13`, `:15`, `:17`.

В authority suite нет SUSPENDED, tampered/missing receipt, reparse/hardlink escape, replacement существующего lock, смены generation во время acquisition, перенесённых ACKNOWLEDGED/UNCONFIRMED записей или phase fault injection до/после ACTIVE. Проверка другой generation в исходном anchor не проверяет гонку acquisition. У consumer suite нет source-origin/fallback случая из F1, выбранного home/CLI output refusal и достаточного контроля wrapper forwarding. Старый test-codex-channel с nullcontext не подтверждает новые authority/lock/cutover свойства; его полный запуск запрещён текущим QA proposal.

Минимальное исправление: добавить адресные synthetic cases либо привязать отдельные точные tests к перечисленным обязательствам до составления admission. Phase failures могут быть покрыты отдельно reviewed operation suite, но отсутствующее покрытие должно оставаться явным gate. Сохранять разделение fake transport tests и реального Windows junction/two-process lock. Это запрос на покрытие принятого договора, а не на полный исторический suite rerun.

## Раздельные вердикты

| Область | Вердикт |
| --- | --- |
| Core source | CHANGES_REQUIRED: F3, F4; совместная tool-origin граница F1 |
| Consumer source | CHANGES_REQUIRED: F1, F4 |
| Consumer test isolation | NOT_ACCEPTED_FOR_EXECUTION: F2 |
| Authority test source | PREPARED_NOT_RUN; неполное покрытие F5, exact runner/cleanup admission ещё требуется |
| Общая coverage | INCOMPLETE: F5; исторические tests не заменяют новый migration evidence |
| Физический Windows lock | Test prepared, NOT_RUN, не PASS |
| Migration/installation | NOT_ACCEPTED; live prerequisites и C64 ограничения неизменны |

В source действительно подготовлены постоянный r+b lock без bootstrap, native volume/file identity, повторная authority проверка после byte acquisition, запрет init reset и обе missing-ledger ветки удалены. Public/CLI аргументы проверяются до AppTools, а observer status читается под lock. Эти наблюдения по тексту не отменяют findings и не являются результатом выполнения.

## Проверенные pins

Base commit `00607be24a608e481efa4437408e7b338fcafe93`.

- source/MANIFEST.json: `2071d287f61ce243730ca6fa75182ddbd877ec9707ba3b541144fd3ef94385d8`.
- consumers/MANIFEST.json: `3e17f22d8e32cea8ff102995aabb1b6f5017baf528b00c857caab992aef3a5a3`.
- architecture/INTERFACE.json: `fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d`.
- QA_SCOPE_PROPOSAL.json: `25df441f261b91d646c20bb05c1856213336509a98731771859d2eb99e2a833f`.
- SOURCE_REVIEW_CARD.json при последнем чтении: `87da137a85d6f58e8f8666f952614015a18183ff9b8027c8d117fd62b23bad75`, status IN_REVIEW_FINDINGS_REPORTED_EXECUTION_BLOCKED, dispatch_attempts=2, первоначальный отказ сохранён.

Все 11 output hashes независимо вычислены и совпали:

| Файл | SHA-256 |
| --- | --- |
| source/staged/bos_dev.py | 5dcd90483a5857fc306002f106a0274b33017049758ebe1926d852b68d099699 |
| source/staged/codex_channel.py | a02012a1d826bacf7ceb9d19e0ff81fad69cb588bdbb28d1a1ed1a85f9d97040 |
| source/staged/test-control-home-authority.py | ed9bc1c41f871321d7761f8075494ed851cef4312e1e2640bbb76710d5afc191 |
| consumers/staged/bos_flow.py | 33d504ca138271844f43a0f2cb4912a6a85ccd22c71ba048d293815140ed233b |
| consumers/staged/local_flow.py | 0592ee17bf2c5a2b2889fb4e01cf88786bd55178e2eac6924b0a315b7054360b |
| consumers/staged/repo_health.py | 29aa2b38ed3da317143adeba90b1b4ca86f9fd6637af98d047870d2c610c8ab8 |
| consumers/staged/bos.ps1 | 4dd3667c776de6cc23d0af8e97444936c7e9dc87f1370ce7f524aeaef3729d12 |
| consumers/staged/bos-flow.ps1 | 8fe945c93e1e05d6b92952a53ff60ab082e20590c520a223fe0697976449af20 |
| consumers/staged/start-workday.ps1 | 5c7999fd1eb238880b9f83bc553d9ab769e45823330869ec6df827be1e70d779 |
| consumers/staged/test-codex-channel.py | 50dcde71cb85e9195da1d9a7c1655c8869cbde0d93661c5758077f26fecfde30 |
| consumers/staged/test-control-home-consumers.py | 0b32479d45e8cc84f14ef2cbd12518d95adb788c0abb471b484b77ccd9940649 |

Девять baseline files также хешированы и совпали с SOURCE_BASES/manifest: два core, flow, три wrappers, channel-test из закреплённого archive и два source-only setup helpers local_flow/repo_health. Прочитаны actual text diffs этих девяти файлов и полный текст двух новых tests. consumer manifest pending provider pins не считается accepted binding: SOURCE_REVIEW_CARD привязывает exact core только для этого совместного review.

## QA classification и оставшиеся условия

NEW по предмету: ACTIVE/PREPARED/SUSPENDED authority, exact C/D alias identity, receipt binding, отсутствие fallback/bootstrap, reparse/hardlink/lock replacement, generation acquisition race, source-origin и phase fault properties именно этого переноса. SAME-PROBLEM при повторном измерении: прежние channel duplicate/id/model semantics, public target guards, flow/wrapper forwarding. Перенесённые records требуют нового transition-specific evidence, но название нового suite не сбрасывает старые бюджеты связанных проверок.

QA_SCOPE_PROPOSAL содержит правильный запрет full historical suite/EOF/C64/app повторов, но пока не является exact run admission. До выполнения нужны исправленные pins, список конкретных test methods и их связь с проблемами/историческими попытками, reviewed runner и независимая приёмка изоляции. P05/fixtures/storage и прочие caps из proposal сохраняются; этот review не подтверждает свободную попытку по каждому старому поведению.

Authority fixture создаёт отдельный TemporaryDirectory, задаёт core constants до resolver, использует реальную Windows junction и отдельный child для byte lock. Cleanup удаляет alias через os.rmdir, затем TemporaryDirectory.cleanup. До admission runner должен подтвердить абсолютную scratch containment и отсутствие неожиданного reparse у QA root, чтобы рекурсивная уборка оставалась внутри назначенного scratch. Проверка alias tag сама по себе не является такой проверкой root. Здесь cleanup не выполнялся. Дочерний процесс должен быть привязан к exact scratch provider и не писать bytecode вне разрешённого дерева.

## Выполненные операции

Только чтение исходного текста, SHA-256, JSON artifact data reads и git diff --no-index. Hash/read/data commands: exit 0. Diff commands: exit 1 означает найденные различия, а не запуск/падение теста. Сохранён только этот allowlisted review-файл; source/consumer/operation/card файлы не изменялись. Коммит не создавался.

helper/test/import/parser/compile/help executions=0; live state/secret reads=0; process/resource/policy/registration probes=0; transport=0; install/copy/activate=0. Raw QA отсутствует, потому что выполнение не допускалось.

Следующий шаг: root возвращает F1/F2/F4 consumer автору и F3/F4/F5 core автору с координацией общей границы F1; затем exact changed bytes проходят независимый review. Operation автор может продолжать своё отдельное source-only покрытие фаз. TECHNICAL_READY=false; PILOT_ALLOWED=false.
