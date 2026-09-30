# UXD02-MONITOR-INPLACE-DRILLDOWN — авторская передача

Статус: **AUTHOR_COMPLETE_REVIEW_PENDING**. Автор не принимает собственный код. Следующий получатель — `bos3_candidate_review`; QA требует отдельного допуска. Полная UXD-02, browser/cross-role acceptance и readiness не подтверждены.

## Exact base и границы

Проверены чистое дерево, ветка `codex/bos3-uxd02-drilldown-20260927` и точный base **`61d9edd32672433713ef0a42ae43a6114c314cc3`**. Result — единственный коммит, содержащий этот отчёт; полный SHA сообщается после создания коммита в финальной передаче, без циклической самоссылки внутри файла.

Прочитаны canonical `docs/orchestration/bos3/evidence/uxd02-scope-20260927/SOURCE_REVIEW_RU.md`, `ASSIGNMENT_REVIEW_RU.md` и observer proposal `NEXT_FUNCTIONAL_SCOPE_FA7E4C7.md`. Их абсолютные пути и SHA-256 сохранены в `SOURCE_AND_CHANGE_MANIFEST.json`. Independent assignment acceptance относится к заданию, не к этому результату.

Изменён только разрешённый frontend source: `DocViewer` readOnly gate, `BoSInspector`, новый `monitorRows`, `homeSelectionVisible`, `BosGlobalMonitor`, `BoSHome`. Generated `assets/app.js` обновлён одной штатной сборкой. `frontend/boss_app_html.html` также штатно сгенерирован, но байты совпали с base; CSS не потребовал изменения. Registry/version/PDF/learning/waiting/control tools/backend/policy/API/DB не изменены. Другие checkout не переключались, subagents не создавались.

## Реальное поведение

Три карточки мониторинга — заказы, производственные работы и партии без допуска — открывают отдельный `kind:'monitor-list'` в существующем inspector. Число карточки и список берутся из **одного** `monitorRows(data,key)` по одному принятому snapshot:

| key | Predicate | Record kind |
|---|---|---|
| orders | Есть связанная line с `b03Positive(b03OpenLine(line))`; эффективный остаток или существующий fallback quantity − shipped. Статус order не добавлен. | orders |
| jobs | status !== done | jobs |
| quality | quantity > 0 и (quality !== approved или missing_documents непустой) | lots |

Обычный `kind:'list'` orders по confirmed status не переиспользуется и не меняется. Tasks и receivable сохраняют прежнюю навигацию section/sub; они не стали точными списками этой карточки.

Выбор списка имеет форму `{kind:'monitor-list', key, monitorOrigin:key}`. При выборе строки проверяются её record kind и фактический ID среди `monitorRows` текущего snapshot. `homeSelectionVisible` повторно проверяет допустимость выбора; неизвестные monitor keys, несогласованный origin и generic list/metric с monitorOrigin не принимаются.

Record selection сохраняет `monitorOrigin` внутри существующего selection. Последующие существующие ссылки inspector проходят `homeSelectionVisible` по тому же snapshot и наследуют исходный ключ; собственного стека истории или копии данных нет. Закрытие записи ведёт к тому же отфильтрованному списку, закрытие списка — к мониторингу. Ключ React inspector включает вид/ID записи, поэтому нативно закрытый dialog при возврате монтируется заново и открывается. Для финального возврата сохранён только DOM opener; это не хранилище бизнес-контекста и очищается вместе с selection. Фактический focus/диалоговый цикл требует отдельно допущенного browser QA.

## Контекст, источник и чтение

Исходные `canUse`, `canInspect`, scope/access revision/epoch/presentation проверки сохранены. Inspector мониторинга рендерится только при ready (`fresh/empty`) и видимом selection. Refresh очищает selection; дополнительно publish любого не-ready состояния в monitor режиме очищает selection/origin/nextSelection. Смена currency/focus/readOnlyOverview/monitor, context drift, denied и session end не сохраняют путь возврата.

Существующий `OrderTrace` не изменён: он выполняет свой guarded trace GET. При успешном открытии его источника после отдельного snapshot reread вызывается `traceSelect`: прежний selection/origin удаляется, overview становится stale, а **в monitor режиме nextSelection=null**. После обновления старый путь и выбранный источник не восстанавливаются автоматически. Ошибки отдельного source read остаются в существующем OrderTrace error lifecycle. Возврат после перечитывания источника не обещается.

В monitor inspector **нет prop onNavigate**. Поэтому существующая кнопка linked Task в OrderTrace disabled и не выводит пользователя в HR. Нет prop onAction; inspector получает `readOnly`, а `BoSHome.begin` дополнительно отвергает monitor режим.

`DocViewer` получил `readOnly=false` по умолчанию. Inspector передаёт ему своё readOnly; ручное подтверждение документа отображается только при `!readOnly && bosCan('write') && current && needs_review`. В обычном режиме прежний write-capable путь сохраняется. Чтение версий/документа и разрешённое скачивание не заменены новым API. Документ не становится редактируемым через read-only inspector.

## Единственный разрешённый запуск

Штатная генерация выполнена ровно один раз:

```text
C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe scripts/build_frontend.cjs
native exit: 0
stdout: JSX compiled; local script assets wired.
stderr: empty
```

`BUILD.json` содержит argv/cwd/time/attempt=1 и SHA-256 входов/выходов. Raw stdout/stderr сохранены без преобразования; `.log` включаются по точным путям с учётом стандартного ignore. После сборки менялись только evidence-документы; их запись использует LF.

Авторский контроль пакета — чтение diff, allowlist и whitespace check. Первая проверка обнаружила CRLF у изменённой строки DocViewer; только эта строка нормализована до единственной сборки. Это исправление формата исходника, не продуктовый тест. Build не повторялся.

**NOT_RUN:** tests/unit/helper/AST/browser/offline visual/HTTP/runtime/lifecycle/DB/init/seed/migrate/reset/training/payment/full/PG/E2E/cross-role. Runtime не устанавливался; endpoint не вызывался инструментами автора. В приложении повторно используются существующие защищённые пути чтения, что не означает их динамической проверки в этой карточке.

## Граничные случаи для отдельного QA

- orders: неподтверждённый order с открытой line входит; confirmed без остатка не входит; несколько открытых lines не дублируют order; effective open=0 перекрывает положительный старый quantity−shipped; fallback остаётся прежним.
- jobs: каждый status кроме done входит; quality: положительная quantity обязательна, quality/documents работают через OR; approved без недостающих документов исключён.
- count/list: exact ID set и число совпадают для всех трёх keys, включая пустой список. `monitorRows(null,key)` и неизвестный key дают []; неизвестный key при этом не допускается как selection.
- selection: key/origin mismatch; чужой ID или неверный kind из первоначального списка; видимые связанные записи; return record→same filtered list→monitor; DOM opener без восстановления в чужой контекст.
- lifecycle: открытый список/запись/DocViewer при refresh, stale/error/denied/context drift/session end/currency change; old callbacks не открывают новую запись; source handoff не восстанавливает nextSelection после refresh.
- readOnly: нет команд/NextAction/manual document review в monitor, нет linked-task route; default-false DocViewer вне readonly сохраняет прежний gate; tasks/receivable остаются generic navigation.
- native UI: открыть/закрыть/ESC/повторно открыть список, связанные записи, вложенный документ, keyboard/focus и узкие размеры. Это предложенные случаи, не выполненные проверки.

Для helper QA извлекать настоящий `monitorRows(data,key)` вместе с `b03OpenLine`, `b03Positive`, `purchaseRemaining`; он возвращает массив исходных row objects без мутации. Input — уже проверенный homeSnapshotShape snapshot. React/state/HTTP/DB для pure helper не нужны. Другие lifecycle/AST проверки требуют отдельно согласованного harness, не запускаются этим отчётом.

Дальше — independent review exact commit/diff/build evidence, затем отдельная QA-карточка и решение единственного root об интеграции. Приёмка задания, успешная сборка и чистый commit не заменяют приёмку продукта.
