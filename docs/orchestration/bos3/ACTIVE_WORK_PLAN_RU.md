# BoS 3.0: действующая очередь работ

Обновление 27.09.2026 по прямому поручению владельца продолжать разработку и уточнению состава предрелиза. Единственный интегратор: root текущего чата 01a0dd56-ca2d-79c0-b159-bde80074a026.

Новый недельный срез владельца: **04.10.2026 23:59 Europe/Berlin**. После срока изменения запрещены; только чтение, итог и штатная пауза существующей automation, приложение не останавливать. 11.10 больше не является разрешённым продолжением. Действующий порядок разработки: DEVELOPMENT_WORKFLOW_RU.md; машинные приоритеты и blockers: CONTROL_STATE.json.weekly_execution. Native goal ведётся в существующем чате контроля, здесь второй цели нет.

## Настройка разработки и следующий шаг

B30-UXD03-DELIVERY завершена: producta753a590727344b73f2c79e142c4c8ec6cc89c0d, evidence correction5f8bd83, immutable runtime3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c (dev.5). Независимый start_overview_review принял фактическую доставку: ACCEPT_SCOPED_DEV5_OWNER_LOCAL_DELIVERY. Capture/stop/apply/start/post-start по одному разу exit0; HTTP200 exact HTML,14 product paths, protected aggregate неизменен, PID35584. Приложение оставлено запущенным. Код, helper QA, пакет, manifest и pins приняты каждый в своём scope; renderer exit UNCONFIRMED сохранён. Полные browser/login/lesson/progress и 3S/8UXD/11 gates не закрыты.

Следующие две owner-blocked линии: B30-12 revision9 ждёт ответа на одно точное исключение обучения наe710; UXD03-WAIT-01 V2 ждёт выбора fixed reason codes либо осознанно shared free text. Оба вопроса уже заданы по одному разу, ответа нет. Root после ответа проверяет exact applicability и независимый manifest/contract review; разрешение не переносится автоматически на dev.5 и не является migration/DB допуском. Сейчас готовая независимая карточка завершена, пустые назначения не создавать. Readiness false; runtime dev5/3d1eabe. При новом feedback оформить конкретный дефект в согласованном объёме.

## История переходов, не текущие назначения

Записи ниже сохраняют состояние на момент каждого перехода. Текущие владельцы и следующая готовая операция находятся выше и в CONTROL_STATE.json.cards / weekly_execution; прежние «готовится», «ожидает» и «следующий шаг» не запускают повторную работу.

B30-UXD03-CARD последовательно интегрирована: author4999f7a -> canonical a5adcefc8a9bf0ff19f522c585fe7114facd7ee3, все четыре product blobs совпали. Independent code/build review + одна NEW pure-helper Node проверка PASS/exit0, отдельный ACCEPT_SCOPED_HELPER_QA. Никакого browser/role/learning PASS. Следующий шаг: новая immutable упаковка версии и review, затем обычная owner-local доставка по standing policy. Установленный runtime пока dev4/e710, рабочая UI-дельта ещё не выдана.

Текущий переход: B30-UXD03-CARD author4999f7a принят bos3_candidate_review как STATIC_CODE_AND_BUILD_EVIDENCE, одна сборка exit0. До root-интеграции отдельный QA исправляет единственный pre-run parser finding в harness: извлечь JSX из HTML перед AST; fixtures/expectations валидны, запусков0. UXD03-WAIT-01 proposal1a8a6c87 получил REVISE: участник/видимость причины, lifecycle/locks/CAS и deactivation recovery не определены полностью. Findings переданы прежнему автору через observer без implementation/migration допуска. Learning revision9 owner question остаётся без ответа.

B30-UXD03-CARD назначена после принятия prep97f03aa: existing design01a0bffa... единственный автор центрального UI, чистая копия bos3-product-design/repo от e710, новая ветка codex/bos3-uxd03-cards-20260927. Allowlist: только Tasks compact-card source и связанные стили, два штатных generated файла и docs/design/evidence-uxd03-20260927/. Показ существующих order/handoff list facts, без waiting/новых прав/истории в списке; reviewer bos3_candidate_review. Одна необходимая сборка новой редакции, проверки отдельно после NEW/SAME-PROBLEM классификации; learning exception не заменяется этой карточкой. Check-in15мин; root интегрирует один принятый коммит и отдельно подтверждает доставку.

B30-UXD03-PREP завершён: existing design передал exact e710 контракт, независимый bos3_candidate_review дал ACCEPT_SCOPED_DOCUMENTARY_PREPARATION без P0-P2. Evidence: evidence/uxd03-prep-20260927/REVIEW_RU.md. Очередь отдела и исполнитель уже существуют; новые compact-card факты можно реализовывать только отдельной карточкой, waiting требует UXD03-WAIT-01. Реализация не назначена. Следующий обязательный шаг недели: ответ на один уже заданный вопрос B30-12 revision9, затем final manifest и независимая проверка pins; до ответа запусков нет.

B30-12 revision9 получил ACCEPT_SCOPED_READY_TO_ASK_OWNER_EXCEPTION, NOT_EXECUTION. Владельцу один раз задан точный вопрос: отдельная synthetic SQLite schema/owner/CEO/один seed и один in-process server-contract прогон трёх кейсов/прогресса, без браузера/сети/повторов/данных сайта. Ответ ещё не получен. После ответа потребуются final manifest с фактическим decision ID и отдельный immutable hash pin-review; до этого запуск запрещён. Source proof checkout e710 чистый и отдельный, БД не создана. Revision8 содержит erratum о неверном static finding importre; никакого runtime FAIL не было. B30-UXD03-PREP продолжает существующий design, не блокируется этим вопросом.

Revision7 B30-12: полный harness написан, но независимый REVISE_BEFORE_OWNER_QUESTION выявил3P1: moving canonical вместо exacte710, недостающие integrity/authorization guards, неполные per-write receipt/state assertions. Root выделяет отдельный source checkout без БД/тестов; тот же QA дорабатывает только свой scratch. Одновременно incoming full-readiness e710 matrix проверяется bos3_candidate_review; общий S1/S2/S3+UXD01–08+11gates scope не заменяется учебными кейсами. Runtime не меняется.

B30-12 revision6: REVISE_BEFORE_OWNER_QUESTION. Независимо подтверждены13 одинаковых source blobs f55->e710, исправленные preview routes и C1 с фактическим пятым CRM шагом. Но oracleline242 ещё требует f55 execution source, а harness является checklist с unconditional refusal. Тот же QA получил конкретную реализацию полного guarded harness в своём scratch без запуска/import/compile. Owner execution question преждевременен; actual code и независимый static review должны быть готовы сначала. Evidence/readiness-scope-20260927/revision6/ сохраняет точный rejected draft. Следующий check-in15мин, не новые product/browser попытки.

Действующий срез после принятой установки dev.4: product7018cca86337da19361951782cffecb09811a89a, runtime/source+manifest e710eb568717dfe3ede945feb899f030bd5ad1ab. Actual capture/stop/apply/start/post-start exit0 по одному разу; HTTP200 exactHTML/version, PID40528/loopback и сохранность protected aggregate подтверждены. Независимый start_overview_review: ACCEPT_SCOPED_DEV4_OWNER_LOCAL_DELIVERY. f55 ниже исторический checkpoint. Следующий текущий исполнитель: existing QA01a0c05d... готовит исправленный exact isolated harness; browser/lessons не разрешены этим переходом. DESIGN_DEV4_CANDIDATE_RU.md и LOCAL_RUNTIME_RECEIPT.json имеют приоритет над историческими next actions ниже.

Паспорт DESIGN_DEV4_CANDIDATE.json принят bos3_candidate_review: ACCEPT_SCOPED_EVIDENCE_PACKAGING, 91/91 точных Git blob hashes. Product7018cca86337da19361951782cffecb09811a89a; отдельный commit паспорта станет immutable runtime source для установки. Это не browser/lesson PASS. Следующий шаг: независимая проверка финальных pins и процедуры доставки.

Актуально 27.09, 15:04Z: dev.4 package принят независимым bos3_candidate_review (ACCEPT_SCOPED_B30_DESIGN_PACK_DEV4), root включает пять файлов и raw PDF evidence. Новая поставка ещё не выполнена. Maintenance template F45E8358 принят start_overview_review только как шаблон; следующий шаг root: exact candidate/manifest/allowlist и независимая pin-delta проверка, затем ordinary owner-local update по действующему разрешению. Runtime пока f55. QA revision4 REVISE_BEFORE_OWNER_EXCEPTION: исправить preview mapping, подготовить безопасный exact isolated bootstrap/harness и полный C1 completion; тот же QA назначен, запусков нет.

Следующая конкретная работа после design integration0cdd3ef: B30-DESIGN-PACK (existing writer, новая isolated bos3-dev4-pack/repo от exact0cdd3ef, толькоversion/README/учебный registry version/PDF/связанные compiled artifacts еслинеобходимо) и B30-DESIGN-DELIVERY-PREP (bos3_fixture_impl, отдельный output qa-scratch/bos3-dev4-delivery-20260927, static guarded runner). Reviewer start_overview_review/bos3_candidate_review независимые. Existing dirty packaging/validation/development worktrees сохранены. Target runtime pin дляdev4 ещёPENDING; текущий f55 не перезапускать. ARCH-02 documentary38c63af принят и переносится безbuild/browser.

Reviewed design source последовательно включён: origin32acfb6 -> root9815ff0, затем origin0d49a89 (brochure/monitor). Оба компонента без конфликтов и без повторов визуальных запусков. Далее ARCH-02 doc correction, отдельная упаковка dev.4 с точным manifest/version и review, затем owner-local delivery по постоянному разрешению. До runtime receipt f55 остаётся выданной версией.

B30-DESIGN-NEXT: получен immutable source pair32acfb6 +0d49a89. Независимый bos3_candidate_review ACCEPT_SCOPED_STATIC_INTEGRATION_B30_DESIGN_NEXT, безP0–P2. Начато последовательное включение: общий visual system первым, brochure/monitor вторым; root evidence/design-integration-20260927/REVIEW_RU.md. Runtime/product package f55 не подменяется промежуточным source; новая упаковка и фактическая доставка отдельно.

ARCH-01: root SQLite proposal исправляется на bos3-fasteners-f55-r1.sqlite3 с полным existing training identity/marker contract, source guard неизменен. Изолированная среда не создана; QA alignment ещё требуется. Exact disposition: evidence/architecture-20260927/ARCH01_DISPOSITION_RU.md. Architect завершил read-only handoff, independent tracker review принят; ARCH-02 wording поручен тому же design owner без rebuild/browser.

Текущий переход 27.09, revision3 B30-12-QA-SCOPE: ACCEPT_SCOPED_PREPARATION_ONLY, статус PARTIAL, не executable plan. Exact immutable artifacts/review: evidence/readiness-scope-20260927/revision3/ и REVISION3_REVIEW_RU.md. Тот же QA получил конкретизацию трёх фактических learning cases на f55 и предложенный root SQLite-only isolation contract; никаких запусков или owner execution question. Более ранний CHANGES_REQUESTED ниже сохранён как история.

Уже назначенный в другом действующем отделе B30-ARCH-CONTRACT-20260927: read-only architect /root/bos3_architect, владелец tracker01a0be90-e790-7351-a8ac-059d523941c4. Только границы данных/прав/freshness и completion proof; output D:/3/BOSDev/repo/outputs/bos3-architect-20260927-143816Z/{ARCHITECTURE_REVIEW_RU.md,HANDOFF.json}. Root не создаёт второго архитектора; сверка независима от detailed QA oracle. Owner assignment reported tracker, продуктовые правки/запуски не разрешены.

| Карточка | Владелец / reviewer | Источник и allowlist | Результат / следующий шаг |
| --- | --- | --- | --- |
| B30-DEV-QUEUE-TRIAGE | bos3_candidate_review, read-only | HEAD 54764b0; только текущие plan/control/team и недельное поручение | DONE_READ_ONLY: независимой готовой продуктовой карточки без допуска/feedback нет; выявлен конфликт сроков 04.10/11.10 |
| B30-DEV-WORKFLOW | root / bos3_candidate_review | Canonical, docs/orchestration/bos3/, BOS3_EXECUTION_RU.md и текущая секция AGENTS.md | DONE: ACCEPT_SCOPED_DEVELOPMENT_CONTROL; единая недельная очередь, blockers/DoD/роли и cutoff. Код CLI 4e014971; review: development-workflow-20260927/WORKFLOW_REVIEW_RU.md. Этот документальный commit завершает карточку; product/runtime не меняются |
| B30-DEV-CONTROL-CLI | bos3_fixture_impl / start_overview_review; отдельный QA bos3_crm_impl | bos3-development-control/repo от 54764b0; только tools/bos_control.py и tools/test_bos3_control.py | INTEGRATED 4e014971: --scope bos3; попытка1 дала 14 PASS + 1 FAIL; после review единственной правки focused attempt2 PASS. Не новый полный suite и не приложение. Evidence: development-workflow-20260927/CLI_REVIEW_RU.md |

Порядок недели: актуальный owner-local кандидат -> светлое превью -> три кейса -> вход/сохранение -> другие согласованные улучшения. B30-PREVIEW-DELIVERY выполнена один раз и принята независимо. Обычные reviewed owner-local обновления разрешены новым «ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ»; старый вопрос больше не blocker. Полное прохождение уроков и новая проверка progress имеют отдельные ограничения. Следующий активный handoff: B30-DESIGN-NEXT, уже выполняется отделом дизайна.

## Приоритет владельца

Последнее прямое уточнение 27.09.2026: вместо тёмной брошюры сделать светлое интерактивное превью, используя найденное старое превью как визуальный ориентир. На одной странице: возможности BoS и три самостоятельно кликабельных кейса. В каждом: исходные факты отдельно от ожидаемого учебного эффекта, передача между отделами, действие, контроль и следующий ответственный. Переключение этапа до входа является только просмотром синтетического сценария, не выполнением задачи. Затем понятный персональный вход в BoS 3.0 с сохранением выбранного кейса. PDF остаётся вспомогательной памяткой.

Дополнительное прямое уточнение того же хода: единый адаптивный дизайн телефона и сайта, узнаваемые значки, смысловые диаграммы и ясный контекст использования; сохранить уместный зелёный акцент старой версии. Вход не подменяет первое знакомство; основной CTA выбранного примера ведёт к обучению. Диаграммы отражают исходные учебные факты, не проценты пройденного урока: обеспечение 140 + 360 = 500 комплектов, качество 250 + 20 = 270 проверенных остатков (не объём отгрузки), оплата 10 000 + 6 400 = 16 400 грн. Дефицит 120 шайб не складывается с комплектами.

Релиз после feedback: доводка локализации, взаимосвязанной работы отделов и оставшихся функций BoS. Не считать весь ERP принятым из-за готовности брошюры. Внешние тестировщики, production и реальные данные не входят в текущую owner-local доставку.

## Точная база

- Canonical: C:/Users/user/.codex/worktrees/bos-consolidation-plan/repo, codex/bos3-prerelease-20260927; исходный SHA этого пакета dd88f28c0779394a70cc1625a6995c6a46f84810.
- Выданный runtime: C:/Users/user/.codex/worktrees/bos3-local-runtime/repo, e710eb568717dfe3ede945feb899f030bd5ad1ab / dev.4. Фактический exact-pin maintenance и single HTML receipt: LOCAL_RUNTIME_RECEIPT.json. Dev.4 browser/JS/login/lessons не проверены; исторический dev.3 entry не переносится. Обычные reviewed local обновления разрешены в принятом объёме без нового вопроса.
- Реализация UI: C:/Users/user/.codex/worktrees/bos3-entry-flow/repo обновлена на defd1fc12545053159a3a888013d096c79157fd3. Шесть прежних файлов совпали с canonical по SHA-256 и сохранены отдельным stash перед switch; stash не применять повторно. Старые WIP не являются базой новых задач.
- Текущий продуктовый кандидат 0.3.0-dev.4: 7018cca86337da19361951782cffecb09811a89a; immutable source с паспортом e710eb568717dfe3ede945feb899f030bd5ad1ab. Паспорт DESIGN_DEV4_CANDIDATE.json. LIGHT_PREVIEW_CANDIDATE.json и f55/dev.3 ниже являются историей. Новый код, выдача на ПК и принятый rc являются разными состояниями.
- Предыдущий dev.2 / ae966d3 сохранён в CANDIDATE_MANIFEST.json и CANDIDATE_ACCEPTANCE_RU.md как историческое доказательство, не текущий product pin. Его maintenance runner нельзя выполнять для dev.3 без нового pin/allowlist и review.

## Текущий пакет светлого превью

| Карточка | Владелец и отдельная копия | Состояние / границы | Зависимость и следующий шаг |
| --- | --- | --- | --- |
| B30-TEAM | Существующий чат «БОС — главный оркестратор», 01a0be90-e790-7351-a8ac-059d523941c4 | DONE_READ_ONLY: старые назначения закрыты/остановлены, копии исторически закреплены; старые пакеты не интегрировал | Root сохраняет единоличную интеграцию; точные назначения ниже |
| B30-PREVIEW-REF | bos3_preview_archaeology; чат «Выполнить план для лендинга BOS» | DONE_REFERENCE_ONLY: Sites v3 public/index.html, landing.css, landing.js на ce0322034971a1ddc5cd66470e3792bb26f56493; отдельный грязный Sites checkout не менять | Композиция и взаимодействия используются как ориентир, не перенос данных/публикации |
| B30-PREVIEW-LIGHT | start_overview_implementation; root интеграция | INTEGRATED_SCOPED_STATIC_BUILD_PASS, aee8d0e; source SHA 5F23F53B... и registry 1BCE8593... | Успешные source-проверки не повторять; browser entry отдельно |
| B30-PREVIEW-REVIEW | start_overview_review; «БОС — отдел дизайна», 01a0bffa-3fc7-7bc2-9868-86164c6e0315 | ACCEPT_SCOPED_STATIC кода + ACCEPT_STATIC UX snapshot, без блокирующих findings | Source/CSS review не доказывает browser UX; полные hashes в evidence/light-preview-20260927/REVIEW_RU.md |
| B30-PREVIEW-PACK | «БОС — реализация и проверка пакетов», 01a0be9f-b413-7822-9f93-16ba69f4f00f; bos3_preview_archaeology reviewer | INTEGRATED_SCOPED_STATIC_PDF_VISUAL_PASS, f55a15d; dev.3, README, PDF/manifest и три готовых рендера | Самостоятельная версия кода, не доказательство доставки или готовности релиза |
| B30-PREVIEW-QA | QA подготовка; root исполнение; start_overview_review независимый reviewer | PASS_SCOPED_ATTEMPT_2_OF_3: 9/9, native exit 0; одна сборка новой ревизии exit 0 | Не повторять успешные проверки. Из-за UNCONFIRMED shell у legacy QA исполнение перенесено root, лимит не сброшен |
| B30-PREVIEW-DELIVERY | root / start_overview_review | DONE: ACCEPT_SCOPED_DELIVERY_AND_ENTRY; capture/stop/apply/start по одному, exits0; desktop1365x900/mobile390x844 и один login | f55 действительно работает; данные сохранены до browser login; выбранный payment not_started. EXECUTION_RU.md, DELIVERY_REVIEW_RU.md и LOCAL_RUNTIME_RECEIPT.json |
| B30-PREVIEW-DELIVERY-PREP | bos3_fixture_impl / start_overview_review | ACCEPT_SCOPED_STATIC, затем использован один раз по прямому допуску; runner F09599F6... | Подготовительный REVIEW_RU.md исторический; исполнение и итог отдельно в EXECUTION_RU.md / DELIVERY_REVIEW_RU.md |
| B30-PREVIEW-RELEASE-REVIEW | «Предложить параллельные процессы», 01a0bf0f-a9e4-7631-87e1-bb1aed03f174 | ACCEPT_SCOPED_EVIDENCE_PACKAGING_ONLY: 12/12 совпали с product commit; manifest 3de8ab13... | evidence/light-preview-release-20260927/REVIEW_RU.md; не общий QA PASS |

Прямой ответ владельца «СДЕЛАЙ ПОЛНЫЙ ПЕРЕХОД ДА» проверен root в исходном чате; затем получено «ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ». Одно окно завершено. Успешную entry-проверку не повторять без новой причины; уроки, ERP/CRM-записи, миграции, reset и прежние исчерпанные наборы этим не разрешены.

История: первый общий ответ про зелёный стиль не считался исключением. Новый точный ответ 27.09 снял прежний blocker; исходный userMessage сохранён в evidence. Установлены ровно reviewed 12 product files f55, а не более поздний docs/dev-tool HEAD.

## История принятого dev.2 пакета

| Карточка | Ответственный | Состояние | Allowlist и результат | Следующий шаг |
| --- | --- | --- | --- | --- |
| B30-04F | start_overview_implementation; start_overview_review; root интеграция | INTEGRATED_SCOPED_STATIC | ae966d3; brochure-first, выбор кейса, отображение передачи/контроля, password boundary | Одна browser entry-проверка только после ответа владельца |
| B30-04C | root; bos3_crm_impl контентный review | INTEGRATED_SCOPED_VISUAL_STATIC | 336f1b4; registry, иллюстрация, PDF, фиксированный PNG asset route, версия | PDF 3 страницы и 4 ссылки проверены; динамический доступ не проверен |
| B30-04Q | start_overview_review; root review harness | PASS_SCOPED_ATTEMPT_1_OF_3 | evidence/entry-20260927/; семь AST checks, native exit 0; одна штатная сборка exit 0 | Успешную проверку не повторять; browser/DB/уроки не входят |
| B30-04D | bos3_fixture_impl; start_overview_review/root | ACCEPT_SCOPED_STATIC_NOT_EXECUTED | evidence/entry-delivery-20260927/; stopped maintenance без init/seed/migrate, pin ae966d3 | Дождаться точного ответа владельца; не запускать capture/apply/stop/start автоматически |
| B30-05G | bos3_crm_impl | SCOPE_CLOSED_STATIC | Read-only трассировка training/service.py -> TrainingHub/CaseRunner/onNavigate; новых блокеров нет | Не выдавать статическую доступность за фактическое прохождение |
| B30-CTRL | root | PUBLISHED_TO_PR10 | 0bdfa47; план, CONTROL_STATE и внешний пакет синхронизированы; automation действует в том же чате | Не дублировать прежний контроль без изменения источников |
| B30-12 | root; bos3_fixture_impl provenance; bos3_crm_impl evidence; bos3_candidate_review independent review | PACKAGED_SCOPED_FULL_QA_OPEN | CANDIDATE_MANIFEST.json, CANDIDATE_ACCEPTANCE_RU.md, evidence/candidate-20260927/REVIEW_RU.md; ACCEPT_SCOPED_EVIDENCE_PACKAGING_ONLY | Полная QA и owner acceptance остаются открытыми; следующий шаг требует решения/нового факта, не повторного аудита |

## История следующих действий dev.3, уже выполнено

1. Независимая сверка LIGHT_PREVIEW_CANDIDATE.json и статическая подготовка maintenance для точного f55a15d завершены. Принятый объём зафиксирован в LIGHT_PREVIEW_CANDIDATE_RU.md. Не выполнять старый ae966d3 runner.
2. Доставка f55 и один desktop/mobile entry приняты независимо. Сохранить выданную версию и raw evidence; owner feedback по фактическому интерфейсу ещё не получен.
3. Синхронизировать новый runtime receipt, текущие control записи и draft PR #10. Main не менять. Фактический локальный URL теперь подтверждён для dev.3.
4. Принять уже готовящийся B30-DESIGN-NEXT handoff верхнего мониторинга и листаемой презентации. Проверить exact base/workspace/allowlist и независимый review; не создавать второго UI автора. Полное прохождение трёх кейсов и внешняя приёмка не покрыты entry.

## Сохранённые границы предыдущего пакета

1. B30-04F/04C интегрированы после независимого review; семь новых AST checks и сборка прошли. Принятый продуктовый SHA зафиксирован выше; документационные коммиты не заменяют его в разрешении на доставку.
2. Проверить новый маршрут в браузере только после отдельного ответа: одна brochure/три выбора/обычный вход, desktop/mobile, без выполнения уроков и записей. Отсутствие ответа не останавливает код, static review, документы и сборку.
3. Доставить reviewed-кандидат на ПК только после отдельного допуска: один controlled stop/update/start, без re-init/seed/migrate; сверить неизменность DB/media/credentials. Не выдавать build за delivery.
4. B30-05G закрыл статическую трассировку трёх кейсов, CRM и возврата. Новых блокеров нет. Динамическое прохождение остаётся отдельным gate; не запускать прежние исчерпанные наборы под новым номером.
5. B30-12: подготовлен единый manifest ae966d3 с десятью delivery artifacts и матрицей применимости evidence. Read-only упаковка не равна завершению QA. B30-12R/owner GO ждут необходимых динамических доказательств; открытые fixture/browser/auth gates не становятся PASS от сокращения состава.
6. После owner feedback: B30-13/Fxx/14, локализация и межотдельные сценарии релиза. Reset-контракт пока не выбран; не удалять/пересоздавать текущую учебную базу.

## Действующий цикл управления

Пока есть разрешенная готовая работа: выдать карточку, дождаться результата, передать независимому reviewer, интегрировать принятое и выдать следующий шаг. Не ограничиваться проверкой mtime/HEAD. Максимум четыре субагента; не создавать конкурирующие чаты/оркестраторы. Если задача уже выполняется, не дублировать. При блокировке одной задачи продвигать независимую часть. Не удерживать все роли занятыми бессодержательной работой.

После принятия read-only паспорта B30-12 не создавать его повторные варианты или новые аудиты неизменного кандидата на каждом heartbeat. До ответа владельца на уже заданные вопросы, нового результата/дефекта или feedback нет основания повторять законченные проверки. Изменение только документационного HEAD не меняет product pin и не является новой QA-причиной. Сохранять тишину при таком неизменном состоянии; не отправлять повторные вопросы.

Существующая heartbeat automation `automation` обновлена штатным инструментом 27.09: ACTIVE, каждые 15 минут, тот же чат. Она продолжает разрешенную очередь, не только наблюдает. Это не гарантия непрерывного процесса при выключенном ПК, закрытом приложении, недоступных инструментах или лимитах. При неизменном не требующем действий состоянии сообщения не повторять.

## Неизменные ограничения

Исторический progress 3/3, отдельное Node-исключение 1/1 consumed; fixture 3/3 correction static-only; init 3/3; успешный start2 и отдельный controlled restart не дают автоматического нового разрешения. P05/A09/A10/A11 и все прежние browser/E2E/PG/full/payment/column ограничения сохранены. NEW B30-04Q имеет собственный узкий oracle, не доказывает работу уроков/БД/браузера. Все исполнения сохраняют native exit, source/hash, raw output, предел попыток.

TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false. 30.09 оценка пробелов/риска, 01.10 фиксация достижимого состава, 02–03.10 разрешённая финальная проверка. До 04.10.2026 23:59 один итог GO/NO-GO с основанием; после срока новых изменений нет, только чтение/отчёт/штатная пауза automation. Прежний 11.10 исторический, не автоматическое продление.

## Новый дизайн handoff

Результат первого QA draft: B30-12-QA-SCOPE CHANGES_REQUESTED, независимый start_overview_review. Недостаёт точных candidate-bound маршрутов/чисел/receipts, S2 mapping, per-run cap classification и определённой synthetic среды. Findings и исходные hashes: evidence/readiness-scope-20260927/REVIEW_RU.md. Действующему QA передана read-only доработка, без execution/owner question; это текущее состояние вместо прежнего IN_REVIEW ниже.

Параллельно B30-12-QA-SCOPE: действующий idle QA получает только read-only подготовку exact browser/lesson/progress decision packet, output D:/3/BOSDev/qa-scratch/bos3-readiness-scope-20260927/. Reviewer start_overview_review; source f55. Никаких новых запусков этим назначением не разрешено. Контракт и DoD: PROJECT_CONTROL_RU.md. Это не повтор реализации исторических карточек.

Дополнение 27.09, 14:15:49Z: tracker подтвердил workspace bos3-product-design/repo, HEAD32acfb6ad3a0aeabe2f7501a28ba878dfeaeec87 и ancestry f55 exit0. Это снимает прежний UNCONFIRMED пути/базы, но не принимает незавершённый patch. Текущий blocker: exact handoff с hashes/allowlist/raw QA от design owner. Следующий check-in существующим heartbeat не позднее15 минут при работающем приложении; готовый результат root принимает сразу.

Карточка B30-PROJECT-CONTROL: DONE, ACCEPT_SCOPED_PROJECTWIDE_DOCUMENTARY_CONTROL. Reviewed внешний протокол включён в PROJECT_CONTROL_RU.md и evidence/projectwide-control-20260927/. Author root, independent reviewer bos3_candidate_review; allowlist только эти документы, ACTIVE/TEAM/CONTROL/DEVELOPMENT_WORKFLOW. Product/runtime f55 не изменяются, application QA не повторяется. Review CANONICAL_REVIEW_RU.md. QA вернул три draft файла, переданные start_overview_review; B30-12-QA-SCOPE пока IN_REVIEW, не новый допуск.

Root прочитал прямое сообщение владельца 01a0e32b-38e4-7653-a0d9-316b6a15ab60 в «БОС — отдел дизайна», thread 01a0bffa-3fc7-7bc2-9868-86164c6e0315. Верхний общий мониторинг и листаемая онлайн-презентация до входа/обучения: B30-DESIGN-NEXT, WAITING_HANDOFF. Отдел уже работает; base/workspace/allowlist/patch ожидаются через существующий запрос проектного контролёра. Новый требуемый product base f55; фактический worker base до ответа UNCONFIRMED. Историческую c8b3 копию не применять вслепую. Root передал новый runtime checkpoint и запрет параллельного canonical/runtime writer. Receipt отправки не является выполнением новой задачи.
