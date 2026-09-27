# BoS 3.0: отделы на текущем задании

27.09.2026. Прямое поручение владельца: найти старое превью, сделать светлый интерактивный старт и перевести отделы на актуальную работу. Это карта исполнителей разработки, не обещание, что все бизнес-отделы продукта уже приняты.

Дополнение по поручению настроить разработку: недельный предел 04.10.2026 23:59 Europe/Berlin; после него только чтение, итог и пауза automation. Порядок и DoD: DEVELOPMENT_WORKFLOW_RU.md. Существующий контролёр 01a0bf0f-a9e4-7631-87e1-bb1aed03f174 ведёт одну native goal, не интегрирует продукт. Новых чатов, целей и расписаний здесь нет.

## Текущая работа настройки

Текущий владелец UXD02-DELIVERY root; candidate manifest review bos3_candidate_review, final pins и actual delivery review start_overview_review. Writer c2d136 завершён и root-integratedd346f63/dev7; template принят статически, targetimmutable ещёнеопределён. Runtime811/dev6 неизменен. Все прежние in-progress packaging/QA ниже исторические.

UI author и UXD02 QA завершены scoped; integrationec96870, runtime пока811/dev6. Сейчас existing writer01a0be9f... выполняет UXD02-PACK в чистой отдельной копии отec96870, reviewer bos3_candidate_review. Delivery template author bos3_fixture_impl и static reviewer start_overview_review завершили TEMPLATE_ONLY; target PENDING, исполнения0. Других параллельных UI редакторов нет.

### История этого перехода

Ниже сохранены промежуточные назначения и нулевые счётчики до их исполнения. Текущие владельцы только в верхнем абзаце и CONTROL_STATE.cards; завершённые роли не переназначать по истории.

Независимая UXD02-DELIVERY-PREP: bos3_fixture_impl готовит только два fail-closed template и отчёт в новом qa-scratch/bos3-uxd02-delivery-20260927; reviewer start_overview_review. From811/dev6, будущий dev7 target PENDING и обязан отказывать; исполнения0. Не меняет runtime или UI, не повторяет старое maintenance окно.

UXD02 автор завершён: design result0f9e94bee39ad7340b47ce762f4ee077726a6ea3; независимый code/build review bos3_candidate_review. Параллельно bos3_crm_impl готовит только новый isolated oracle, execution0, reviewer start_overview_review после подготовки. Shared UI не получает второго автора, runtime не меняется.

Dev.6/8114097 установлена и принята независимо; root завершил доставку, приложение оставлено работать. B30-CONTROL-MANIFEST завершён: author bos3_fixture_impl, QA bos3_crm_impl, reviewer start_overview_review; приняты разные exact revisions с run1 четырёх методов и run2 одного нового метода, без повторов. Текущий автор UXD02: design01a0bffa-3fc7-7bc2-9868-86164c6e0315, reviewer bos3_candidate_review; clean bos3-product-design/repo от61d9edd, codex/bos3-uxd02-drilldown-20260927. Shared UI имеет одного автора. Source explorer завершён. Одна генерация разрешена, QA и доставка отдельно. Остальные завершённые роли не получают дубликатов; B30-12 и UXD03-WAIT требуют прежних owner decisions.

Следующие абзацы сохраняют промежуточные handoff этой поставки. Действующие назначения только выше и в CONTROL_STATE.cards.

UXD01-PACK уже принят независимо и интегрированfa7e4c7; writer завершён. Текущий UXD01-DELIVERY: root, manifest reviewerbos3_candidate_review, finalpins/actualdelivery reviewerstart_overview_review. Runtime до новогоreceipt остаётсяdev5/3d1. B30-CONTROL-MANIFEST: bos3_fixture_impl, только scratch/bos3-control-manifest-20260927/tools/{bos_control.py,test_bos3_control.py} и отчёт; noexecutionдоreview. Он исправляет новый конкретный stale-manifest defect служебного CLI, не appchecks. Старыйdirtybos3-development-control сохранён.

UXD01-PROVENANCE-QA завершена: bos3_crm_impl выполнил reviewed oracle correction и focusedattempt2/3 PASS/exit0; independentstart_overview_review ACCEPT_SCOPED_AST_PRESENTATION_DISCLOSURE. Run1FAIL сохранён; повторов не назначать. Design0338 интегрирован8eb832a, writer57d9 интегрированfa7e4c7, оба автора завершены. Текущие исполнители доставки и отдельной CLI-коррекции указаны выше; runtime до новой квитанции dev5/3d1.

UXD01-DELIVERY-PREP: bos3_fixture_impl, отдельный новый scratch, static-only шаблоны следующего обновления from3d1/toPENDINGdev6; reviewer start_overview_review. UI source не трогает, runtime/test execution0. Зависит от принятого будущего package и final-pin review; текущий dev5 остаётся работающим.

UI-автор design01a0bffa-3fc7-7bc2-9868-86164c6e0315 завершил UXD01-PROVENANCE-DISCLOSURE, author0338 в clean bos3-product-design/repo. Source mapping explorer также завершён. Code/build reviewer bos3_candidate_review и отдельный QA reviewer start_overview_review дали scoped verdict. Не выдавать завершённую работу повторно. Две owner questions блокируют только свои линии, не упаковку и обычную доставку принятой UXD-01 части.

Root доставил exact dev.5/3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c после независимого manifest/final-pin review. start_overview_review принял actual raw delivery как ACCEPT_SCOPED_DEV5_OWNER_LOCAL_DELIVERY;5этапов exit0, HTTP200 exactHTML, protected aggregate сохранён. Producta753a59, correction5f8bd83; documentation HEAD отдельно. Design, writer, helper QA, template author и оба reviewers завершили scoped карточки; не занимать их повторным аудитом. Следующие learning и waiting требуют уже запрошенных owner decisions. Root хранит зависимости, observer контролирует, dirty старые worktrees сохранены. Renderer exit UNCONFIRMED и все readiness false.

UXD03-WAIT-01 V2 завершил независимый review с одним disclosure decision; ответ ожидается. B30-12 имеет отдельный уже заданный вопрос, привязанный кe710. Эти линии не запускаются до ответа. Для нового UXD-01 разрешена конкретная реализация уже обязательного требования; она не является повтором lesson/fixture/browser QA или отменой их лимитов.

## История назначений, не действующая очередь

Все записи ниже датируют предыдущие передачи. Фразы о подготовке/review и нулевых запусках относятся к тем моментам; текущее завершённое CARD/helper QA и активная упаковка определены выше и в CONTROL_STATE.json.

Design B30-UXD03-CARD и отдельный helper QA завершены scoped: accepted author4999f7a интегрирован root как a5adcefc8a9bf0ff19f522c585fe7114facd7ee3. Reviewer кода bos3_candidate_review; reviewer одного PASS/exit0 pure-helper run start_overview_review. Авторы не приняли себя, повторов нет. Следующий владелец новой упаковки назначается отдельно; runtime до точного receipt остаётся dev4/e710.

UXD03-WAIT-01: новый source-bound proposal контролёра (1a8a6c87...) передан отдельному независимому bos3_candidate_review. Только read-only contract review на clean learning-proof/e710: policy участника/причины, lifecycle, CAS/replay/locks и migration boundary. Backend implementation/migration не назначены; текущий автор UI не переназначается. Root принимает disposition отдельно от полноты UXD03.

B30-UXD03-CARD-QA: bos3_crm_impl готовит отдельный pure-helper Node harness только в qa-scratch/bos3-uxd03-card-qa-20260927; reviewer start_overview_review, exact final author SHA пока dependency. Никаких запусков. Это новая presentation-дельта, не повтор fixture/progress/browser/membership; лимиты сохраняются. Автор UI и автор теста разные.

Следующая активная B30-UXD03-CARD: тот же design01a0bffa... / bos3_candidate_review, workspace bos3-product-design/repo, branch codex/bos3-uxd03-cards-20260927, basee710. Единственный UI автор; allowlist и DoD в CONTROL/ACTIVE. Только карточка существующих list-safe facts и её стили/generated outputs; waiting/backend/runtime вне scope. Предыдущая prep закрыта, её повтор не назначается. QA learning ожидает уже заданный owner exception независимо от этой карточки.

B30-UXD03-PREP завершён автором 15:43:26Z, turn01a0e37d-ca24-7101-a9f9-e685f1ab4754. Reviewer bos3_candidate_review дал ACCEPT_SCOPED_DOCUMENTARY_PREPARATION; точные артефакты и verdict: evidence/uxd03-prep-20260927/. Design больше не занят этой карточкой. Waiting semantics требует отдельного решения, UI-реализация пока не назначена. QA revision9 ожидает фактический ответ на уже заданный вопрос; новых запусков нет. Записи о продолжающейся подготовке ниже являются историей.

QA author01a0c05d... завершил revision9 статически; independent start_overview_review ACCEPT_SCOPED_READY_TO_ASK_OWNER_EXCEPTION, NOT_EXECUTION. Root запросил одно точное исключение bootstrap+learning run; owner ответ ожидается, новых запусков0. Автор не выполняет harness самостоятельно. Следующий получатель после фактического ответа: root формирует finalmanifest, reviewer проверяет ID/hash/value, затем root определяет единственного исполнителя. Existing design B30-UXD03-PREP всё ещё работает в своём output-only scope.

Новое независимое B30-UXD03-PREP: existing design01a0bffa-3fc7-7bc2-9868-86164c6e0315, ранее чистая отдельная bos3-product-design/repo переведена root на detached e710, прежняя branch38c63af сохранена. Только source read-only и два output файла в qa-scratch/bos3-uxd03-prep-20260927; reviewer bos3_candidate_review, check-in15мин. Разделить существующие list-safe факты, guarded detail/history и отсутствующие waiting semantics, без реализации. QA получил отдельный чистый immutable bos3-learning-proof/repo e710; его scratch и будущая DB не изменялись root, executions0.

QA revision6 source applicability принята статически, executable harness не принят (два P1). Active owner01a0c05d-6eeb-79f1-a135-be66985b442f, тот же scratch, следующая операция полный guarded source без исполнения; reviewer start_overview_review. Root не задаёт вопрос о неприготовленной проверке. Tracker отдельно завершил B30-DEV4-CONTROL-CONTEXT: единственный checkpoint paragraph существующей automation переведён на dev4, независимый ACCEPT_SCOPED и native saved-prompt verification, id/ACTIVE/15min/target/cutoff сохранены. Evidence D:/3/BOSDev/repo/outputs/bos3-dev4-control-sync-20260927/; новых таймеров нет.

Текущий источник для новых заданий: reviewed product7018cca86337da19361951782cffecb09811a89a, установленный runtime e710eb568717dfe3ede945feb899f030bd5ad1ab (добавлен паспорт), dev.4. Root выполнил новое обычное обновление, данные сохранены; start_overview_review принял raw delivery evidence, bos3_candidate_review сверяет контрольные записи. Existing quality01a0c05d... продолжает только статический исправленный learning harness от f55 с обязательной applicability-сверкой finaldev4 перед любым предложением запуска. Writer/design/architect завершили свои карточки; незавершённые старые копии сохранены. Дальнейшие старые указания f55 или WAITING_HANDOFF ниже являются историей.

27.09 15:04Z: writer завершил dev.4 package в bos3-dev4-pack/repo, base0cdd3ef; bos3_candidate_review ACCEPT_SCOPED_B30_DESIGN_PACK_DEV4. Root последовательно интегрирует; runtime ещё f55. bos3_fixture_impl завершил guarded template F45E8358, start_overview_review ACCEPT_SCOPED_TEMPLATE_ONLY; final pin review и установка остаются у root. Тот же quality исправляет revision4 oracle и готовит статический exact harness после REVISE_BEFORE_OWNER_EXCEPTION, без исполнения. Дизайн и архитектор завершили принятый scope, повторные задания им не выданы.

QA scope revision3 принят start_overview_review только как уточнение границ, не готовый run plan. Status PARTIAL; существующий quality продолжает exact lesson/service/receipt oracle в прежнем scratch. Root выбрал конкретное SQLite-only предложение среды, но не создал её и не снял caps. Новое смежное назначение tracker: B30-ARCH-CONTRACT-20260927, /root/bos3_architect read-only, reported by01a0be90...; две output-only записи, без canonical/design/runtime edits или subagents. Это учитывается в лимите исполнителей, не новый root.

Текущая новая подготовка QA: B30-12-QA-SCOPE, существующий QA чат 01a0c05d-6eeb-79f1-a135-be66985b442f после подтверждения idle; отдельный output bos3-readiness-scope-20260927, product f55, reviewer start_overview_review. Только матрица требований/существующего кода/evidence и точный план допусков, без запусков/субагентов. Observer сообщил ACTIVE своей native goal; root не создаёт новую и не превращает это в полную приёмку.

- Root: B30-DEV-WORKFLOW завершён в этом документальном commit; канонические plan/control/сроки и PR согласованы. Независимый reviewer bos3_candidate_review: ACCEPT_SCOPED_DEVELOPMENT_CONTROL, предыдущий P1 закрыт фактической интеграцией CLI.
- bos3_fixture_impl: B30-DEV-CONTROL-CLI завершён, root интегрировал 4e014971e5db33f9106de86399424bedf2ca15bb. Выделенная копия bos3-development-control/repo от 54764b0; только tools/bos_control.py и tools/test_bos3_control.py. Независимый reviewer start_overview_review; QA bos3_crm_impl сохранил первый FAIL и одну успешную focused-проверку без полного повтора.
- bos3_candidate_review: завершил новую матрицу очереди по недельному поручению; готовых независимых продуктовых карточек без нового допуска/feedback не выявил. Это не повтор продукта или manifest.
- B30-PREVIEW-DELIVERY: root выполнил одно окно, start_overview_review принял actual receipts/screenshots: ACCEPT_SCOPED_DELIVERY_AND_ENTRY. Dev.3 запущена, прежний permission blocker снят.

## Управление и актуальная база

- Единственный интегратор: root чата «Подготовить план консолидации BoS», 01a0dd56-ca2d-79c0-b159-bde80074a026.
- Canonical: C:/Users/user/.codex/worktrees/bos-consolidation-plan/repo, codex/bos3-prerelease-20260927.
- Текущий продукт: dev.4 / 7018cca86337da19361951782cffecb09811a89a; выданный immutable runtime/source+manifest e710eb568717dfe3ede945feb899f030bd5ad1ab. Исторические defd1fc/aee8d0e/f55 и dev.1-dev.3 сохранены с их исходными scopes. Docs/dev-tool HEAD не заменяет product pin. Dev.4 delivery подтверждён, browser/JS/login/lessons на нём не приняты.
- Не больше четырёх одновременно работающих исполнителей; новые чаты, второй интегратор и scheduler не создаются. Автор не принимает собственный код.

## Почему отделы оставались на старой версии

Сверка реальных чатов показала завершённые или остановленные прежние задания и исторически закреплённые отдельные копии. Новая ветка root не обновляет их автоматически. У отдела дизайна завершилось прежнее membership-задание, у QA было закрытие v17, у реализации сохранились старые v19 пакеты. У прежнего главного оркестратора осталось состояние подготовки до нового START. Это не причина применять старые пакеты поверх нового кандидата.

Root сохранил прежний UI WIP, подтвердив совпадение шести файлов с интегрированным dev.2 по SHA-256, и переключил свободную UI-копию на defd1fc. Упаковка получила отдельную чистую копию от того же SHA. Недоступность shell в чате дизайна зафиксирована UNCONFIRMED; ему передан фактический diff, полученный root с exit 0, для ограниченного review по snapshot.

## История назначений принятого f55

| Исполнитель | Фактическое новое поручение | Источник и запреты |
| --- | --- | --- |
| «БОС — главный оркестратор», 01a0be90-e790-7351-a8ac-059d523941c4 | Завершил read-only инвентаризацию отделов, старых баз и причин остановки | Не интегрирует и не раздаёт параллельные задания; старые v19 пакеты не применял |
| bos3_preview_archaeology | Нашёл светлый Sites v3 и исторический receipt | D:/3/ChatGPT/бос/site/public/ на ce0322034971a1ddc5cd66470e3792bb26f56493; reference only, грязный checkout не меняется |
| «Выполнить план для лендинга BOS», 01a0bec4-431a-7d81-b858-a18ca96bd0af | Завершил светлый дизайн-brief и сверку композиции/арифметики | Никаких Sites публикаций, переносов данных «Опоры» или новой реализации |
| start_overview_implementation | Реализовал светлый preview, три выбора, локальный просмотр передач, диаграммы и светлый вход | bos3-entry-flow/repo; frontend/boss_app_source.html и только presentation.chart в frontend/bos3_content.json |
| start_overview_review | ACCEPT_SCOPED_STATIC кода; указал необходимую адаптацию entry oracle | Независимый read-only review; не выдаёт его за браузерную приёмку |
| «БОС — отдел дизайна», 01a0bffa-3fc7-7bc2-9868-86164c6e0315 | ACCEPT_STATIC финального UX/CSS/chart snapshot | Не работает в старой c8b3 копии; результат ограничен diff snapshot, shell access UNCONFIRMED |
| «БОС — реализация и проверка пакетов», 01a0be9f-b413-7822-9f93-16ba69f4f00f | Завершил dev.3, README и PDF/manifest; независимый review bos3_preview_archaeology принят | Результат интегрирован f55a15d; три страницы PDF просмотрены, runtime не затронут |
| QA, чат 01a0c05d-6eeb-79f1-a135-be66985b442f (название не задано) | Подготовил адаптированный AST oracle; финальное чтение source было UNCONFIRMED | Root завершил chart assertion, получил независимый review и выполнил ровно попытку2/3: 9/9 PASS и одну сборку exit0. У QA нет параллельного исполнения |
| «Предложить параллельные процессы», 01a0bf0f-a9e4-7631-87e1-bb1aed03f174 | ACCEPT_SCOPED_EVIDENCE_PACKAGING_ONLY на f55a15d: 12/12 artifact hashes и bytes, receipts, source vs runtime | Read-only, без старого v19 recovery, HTTP, тестов и серверных действий |
| bos3_fixture_impl | Подготовил immutable maintenance pin f55a15d и allowlist dev.3; независимый start_overview_review принял статически | Runner сохранён в evidence/light-preview-delivery-20260927/; не исполнялся, runtime неизменен |

## Контроль результата

Root забирает законченный результат, сверяет diff/hash/allowlist, получает независимое review, интегрирует последовательно и передаёт следующую готовую карточку. Активность чата не является результатом. Не держать роли занятыми повторными аудитами неизменного кода.

Существующая automation `automation` обновлена штатным инструментом на светлое превью и ту же root-очередь. Период 15 минут, ACTIVE; она не гарантирует непрерывную работу при выключенном ПК, закрытом приложении или недоступных инструментах. Новые таймеры не созданы.

Точные состояния карточек и code/evidence/review/runtime pins: ACTIVE_WORK_PLAN_RU.md, CONTROL_STATE.json и LOCAL_RUNTIME_RECEIPT.json. Доставка и scoped entry dev.3 приняты; полная browser/lesson/release acceptance остаётся открытой. TECHNICAL_READY/PILOT_ALLOWED/MVP=false.

## Новое текущее поручение дизайна

«БОС — отдел дизайна» (01a0bffa-3fc7-7bc2-9868-86164c6e0315) выполняет прямой новый scope: верхний мониторинг и листаемая презентация перед входом/обучением. Карточка B30-DESIGN-NEXT; текущий turn 01a0e32b-3715-7df3-9a1a-83754c3f36af подтверждён root read_thread. Контролёр сообщил children learning_design 01a0e303-635d-7131-bc2d-4ac3dede3ddc, design_coverage 01a0e301-cc1e-7b32-a8ec-30e76ad2fe62, visual_qa 01a0e304-03b1-7461-aa70-86bebe158775. Это reported roster, не подтверждение их source/готовности. Base/workspace/allowlist/patch handoff ожидается; root не дублирует UI реализацию. Старое ACCEPT_STATIC в таблице выше относится только к принятому f55, не новому поручению.

Обновление handoff 14:15:49Z: проектный контролёр подтвердил actual C:/Users/user/.codex/worktrees/bos3-product-design/repo, branch codex/bos3-product-design, HEAD32acfb6ad3a0aeabe2f7501a28ba878dfeaeec87; f55 ancestor exit0. Прежний UNCONFIRMED пути/базы снят. Exact patch/hash/allowlist и окончательные review/QA ещё ожидаются; WIP не принят. Новая действующая матрица всех ролей и передачи: PROJECT_CONTROL_RU.md. Историческая таблица выше не выдаёт повторных поручений.

Свежий отчёт проектного контролёра: writer 01a0be9f... признал f55 и не запускает повторную упаковку; quality 01a0c05d... прочитал текущие control/manifest, прежний UNCONFIRMED именно для metadata access снят. Это не новая QA или полный доступ к runtime. Точные внешние snapshots: outputs/bos3-projectwide-control-20260927/CONNECTIONS_AUDIT.json и TASKS.json в D:/3/BOSDev/repo; новый canonical closeout имеет приоритет над промежуточным hash snapshot.
