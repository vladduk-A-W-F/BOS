# B30-DEV-CONTROL-CLI: независимое ревью и QA

27.09.2026. Автор bos3_fixture_impl; reviewer start_overview_review; отдельный QA bos3_crm_impl; root интегратор. Изолированная копия C:/Users/user/.codex/worktrees/bos3-development-control/repo, base 54764b0ac33e7e7a0f044a21a7ea1899410b6fb8. Allowlist: tools/bos_control.py и tools/test_bos3_control.py.

## Причина и изменение

Исторический read-only inspector читал только старые STATE/QUEUE. Добавлен явный --scope bos3 для status/context/plan/card/validate; legacy default и validate сохранены. Current card lookup не возвращает historical_cards. Status отделяет product/runtime/readiness, вычисляет cutoff без side effects и всегда пишет execution_authorized_by_tool=false, requires_live_owner_instruction=true.

Validator проверяет непустые 40-hex pins и версии, их соответствие manifest/receipt, false readiness, уникальные текущие ID, отсутствие исторического dispatch, различие активного owner/reviewer, записанное разрешение и optional weekly contract. Валидная заблокированная конфигурация может дать PASS только согласованности управления, не продукту.

## Findings и исправления до исполнения

1. P1: два отсутствующих pins могли сравниваться как None == None. Исправлено проверкой обязательных полных pins и непустых версий; negative test добавлен.
2. P2: текущий pending/BLOCKED был единственным допустимым будущим состоянием. Добавлены только recorded статусы AUTHORIZED_ONE_SHOT и CONSUMED_ONE_SHOT с owner_message_ref, точным pin/scope и outcome/result для consumed. Запись не разрешает исполнение. Pending строго требует BLOCKED; DONE требует evidence.
3. P2: optional weekly ошибочно стал обязательным при pending. Optional восстановлен: без него cutoff=null, при его наличии весь контракт проверяется. Сам delivery-card остаётся BLOCKED. Негативные и переходные synthetic проверки добавлены до первого запуска.

Итог независимого review перед первым запуском: ACCEPT_SCOPED_CODE_AND_ORACLE, без тестовых запусков reviewer. SHA-256 первой проверенной редакции:

- tools/bos_control.py: 80E74C8BB56D3F0BBFDC6BF88016AC151833AC3C60EF783611CC3FEA339E91BB.
- tools/test_bos3_control.py: 8E561EF108B6030F3703264928DFD727FD6BD7647D9E19791F0862AB4AF67CC1.

## Разрешённая проверка

Классификация NEW_DEVELOPMENT_CONTROL_NOT_PRODUCT_QA. Отдельный QA получил ровно один запуск `D:/3/BOSDev/venv/Scripts/python.exe -B -m unittest tools.test_bos3_control` на этих байтах. До результата этой записью PASS не заявляется. Harness использует только временные synthetic JSON/text и стандартную библиотеку; не запускает приложение, Django, HTTP, браузер, Git, БД или lifecycle. При неудаче автоматического повтора нет. Исторические fixture/progress/full/PG/E2E/browser/payment лимиты не изменяются.

Фактическая попытка 1/3: native exit 1, 15 tests, 14 PASS и один FAIL. test_scope_routes_context_to_bos3_not_legacy обнаружил дополнительную пустую строку: ожидалось `bos3 context\n`, получено `bos3 context\n\n`. QA ничего не исправлял и не повторял. Root назначил автору узкое исправление вывода bos3 context/plan без изменения теста и legacy ветки. Затем требуется независимый delta review и ровно одна проверка только упавшего метода; полный набор не повторять. Исходный FAIL сохраняется.

## Исправление и принятый результат

Автор добавил только `end=''` в BoS 3 document print. Независимый start_overview_review принял точечную правку: она не меняет validation, pins, permissions или legacy. Утверждена одна проверка упавшего метода, без полного повтора.

Попытка 2/3: `D:/3/BOSDev/venv/Scripts/python.exe -B -m unittest tools.test_bos3_control.Bos3ControlTest.test_scope_routes_context_to_bos3_not_legacy`, 1 test, OK, native exit 0. QA bos3_crm_impl. Итог: 14 успешных проверок на первой редакции и одна успешная focused-проверка на исправленной; не новый общий 15/15 запуск. Исходный FAIL не удалён. Argparse usage в первом stderr ожидаем из negative case отказа исторической карточке.

Принятые байты, совпавшие после интеграции root:

- tools/bos_control.py: 40A3C7FCA94E75EDADD7DF5FEAC2ED889E50F2C46BF997E655D23E59F05ABA63.
- tools/test_bos3_control.py: 8E561EF108B6030F3703264928DFD727FD6BD7647D9E19791F0862AB4AF67CC1, тест не изменён.

Raw stdout/stderr/native-exit и receipts сохранены рядом как attempt-1.* и attempt-2.*. SHA-256 receipts: 94783E8F08E00BC1DD71DCE844528CA5A935706BAB1BD447E48FC08A76CF4FCA и 26E600A3FD741ED26AB68C5F4E9EE7E7FD882ED9339FD112A868D7A525E04036. Verdict: ACCEPT_SCOPED_INFRASTRUCTURE_WITH_FOCUSED_FIX. Остаток 1/3 не является разрешением повторять успешные проверки.

Product pin f55a15d и runtime 33d7d38 не изменяются этим dev-tool commit. Реальная read-only сверка новых управляющих документов фиксируется отдельно; продуктовые тесты, browser и runtime здесь не запускались.
