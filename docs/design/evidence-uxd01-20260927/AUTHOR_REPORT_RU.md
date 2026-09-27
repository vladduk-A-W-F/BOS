# UXD01-PROVENANCE-DISCLOSURE — авторский отчёт

Статус: **AUTHOR_COMPLETE_REVIEW_PENDING** после единственного коммита карточки. Автор не принимает собственный результат. Следующий получатель — независимый `bos3_candidate_review`; полная UXD-01, browser и cross-role acceptance остаются открыты.

## Версия и разрешённый объём

- Base: `3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c`.
- Ветка: `codex/bos3-uxd01-provenance-20260927`; исходный HEAD/branch/чистое дерево проверены перед изменениями.
- Result: единственный коммит, содержащий этот отчёт. Его полный SHA сообщается в финальной передаче после commit, без циклической самоссылки внутри файла.
- Классификация интегратора: `NEW_PRESENTATION_DISCLOSURE`.
- Editable: только `BosGlobalMonitor` и его `if(monitor)` caller в `frontend/boss_app_source.html`; связанные `.bos-monitor-*` стили в `frontend/bos_design.css`.
- Generated-only: `frontend/boss_app_html.html`, `assets/app.js`.
- Evidence-only: этот каталог. Нет изменений backend/rights/model/DB/learning/waiting/version/registry/PDF. Другие checkout не переключались, чужие изменения не отменялись, субагенты не создавались.

## Поведение

Каждая из пяти существующих метрик получила отдельный native details-блок «Про показник». Основная кнопка по-прежнему открывает существующие section/sub; disclosure — соседний элемент, не вложенный интерактивный control. Блок раскрывает источник, правило подсчёта, охват, отсутствие отдельного филиального/календарного фильтра, бизнес-дату, время чтения, неизвестное время изменения источников, границу объяснения отклонений и следующий доступный переход.

Формулы, число метрик, source request и выбранные destination не меняются. Финансовая карточка и её данные остаются за существующим `bosCan('finance')`. Недоступный destination остаётся disabled и сопровождается сообщением о недоступности перехода. Конкретные record IDs, причины задержек, плановые отклонения и новые фильтры не создаются.

`ready` по-прежнему определяется исходными `fresh/empty` и scope guards. Значение, unit, warning tone, note и **весь блок текущих source/time/scope facts** не выводятся при loading/refreshing/stale/error/denied/context-drift. Вместо них — сообщение об очищенных/скрытых сведениях. Не менялись `refresh`, `canUse`, cancellation, identity/access revision, presentation-context gate или navigation callback. Статический footer больше не раскрывает предыдущую businessDate в неготовом состоянии.

Заголовок «Показники поточного читання» не обещает универсальную полноту компании. Каждый показатель описывает свой источник; данные не смешиваются с другим кэшем. Нет новых fetch, прав, command dispatch, storage, автоматического обновления или background polling.

## Источник, охват, время

Единственный запрос остаётся `GET /api/erp/snapshot/` без branch/period query. `erp/views.snapshot` создаёт `Policy`, вызывает `erp.queries.snapshot(policy)` и добавляет home: CEO через `experience.home`, остальные через scoped Task projection. ERP arrays проходят существующую policy/projection; финансовый home выдаётся CEO, а не всем ролям.

`at` устанавливается `new Date().toISOString()` в браузере после JSON/shape/context проверок. UI подписывает его «Прочитано у цьому вікні», показывает дату, время и часовой пояс устройства. Это не timestamp изменения данных. `as_of` задаётся `operations.service.as_of`: Configuration dataset.as_of, иначе date.today(); валидируется `homeBusinessDate` и подписывается «Бізнес-дата розрахунку». Это не календарный период и не отметка обновления источников.

Источники/формулы конкретных метрик и точные хеши прочитанных файлов фиксируются в `SOURCE_AND_CHANGE_MANIFEST.json`. UI использует понятные названия реестров; технический route и backend формулы доступны ревьюеру в evidence, а не выдаются за новые продуктовые переходы.

Сверено с final source-contract, переданным интегратором для exact base. В inventory используется фактический путь `boss_project/policy.py`, а не опечатка `operations/policy.py` из сообщения.

| Метрика | Реальное правило (без изменения расчёта) | Существующий переход |
|---|---|---|
| orders | Один order, если есть связанная line с `b03Positive(b03OpenLine(line))`; open_quantity, иначе quantity − shipped. Order status не фильтруется. | ERP → Продажі (`erp/sales`) |
| jobs | `jobs.filter(status !== 'done').length` | ERP → Виробництво (`erp/production`) |
| quality | `quantity > 0 && (quality !== 'approved' || missing_documents.length)`; условие подсчёта не выдаётся за причину сбоя. | ERP → Якість і зміни (`erp/quality`) |
| tasks | Неархивные home.tasks со status !== done; число просроченных использует серверный is_overdue. | HR → Доручення (`hr/tasks`) |
| receivable | Выбранный home.financial.currency; сумма invoice.open. `money_open → invoice_settlement`: max(amount − active credits − paid, 0); held retentions не вычитаются (collectible — другой показатель). | ERP → Фінансовий результат (`erp/costs`) |

Source references: `erp/queries.py:83–138`, `erp/views.py:16–19`, `erp/experience.py:62–78`, `erp/balances.py:66–74`, `operations/projections.py:42–77`, `operations/service.py:16–18`, `tasks/queries.py:12–14`, `boss_project/policy.py` (policy contract от интегратора). Whole-installation scope CEO не переносится как обещание всем ролям; UI говорит о записях, доступных текущему аккаунту. Филиальный и календарный фильтры отсутствуют, businessDate не означает историческое состояние «на дату».

## Layout и доступность в исходнике

Сохранены текущая светлая палитра, desktop auto-fit сетка и мобильная горизонтальная лента. Native details/summary доступны с клавиатуры. Новый scroll region имеет имя, tabIndex и видимый focus; высота содержимого ограничена `min(34dvh,280px)`, чтобы раскрытие не вытесняло всё рабочее пространство. Summary минимум 44 px; перенос длинных текстов разрешён. Показатели по-прежнему скрываются общей кнопкой collapse.

Это свойства реализации; фактическая геометрия, экранный диктор, клавиатура и мобильные размеры **NOT_RUN**. Новые скриншоты/браузер/визуальный harness не запускались.

## Проверки и ограничения

Разрешён только один штатный запуск `node scripts/build_frontend.cjs`. Точный argv/runtime path, исходные stdout/stderr, native exit, времена и input/output hashes сохраняются в `BUILD.json` и соседних `.log`. Повтор сборки запрещён. Build generation не является продуктовым QA и не запускает learning harness.

Фактический запуск выполнен один раз: **native exit 0**, stdout `JSX compiled; local script assets wired.`, stderr пустой. После него изменялись только evidence-документы; исходники и сгенерированные файлы совпадают с хешами этой сборки.

Контроль пакета: прочитанный diff, точная allowlist, `git diff --check`/staged whitespace check; JSON evidence записывается LF, два raw log включаются в Git явно, поскольку общий ignore исключает `.log`.

**NOT_RUN:** любые unit/targeted/helper tests, browser/offline visual, HTTP/network, runtime/lifecycle, DB/seed/reset/migrations, training/payment/full/PG/E2E и cross-role динамика. Эти ограничения следуют карточке интегратора, не являются PASS. Runtime и readiness не менялись.

Предлагаемые случаи для отдельно допущенного QA: пять источников и существующие destinations; отсутствие branch/period фильтров; финансовые роли/валюта; ноль против неизвестного значения; fresh→refreshing/stale/denied/context-drift с уже открытым disclosure; неверный/отсутствующий as_of; чтение в другую дату и timezone; unavailable destination; длинный текст, 390/768/1440 и 200%, Tab/Enter/Space/scroll/collapse. Этот список не разрешает запуск и не подменяет independent harness review.

Commit и успешная генерация не подтверждают полную UXD-01, истинность производственных данных, корректность прав в runtime или выпуск. Итоговый exact result SHA и фактический native build exit передаются независимому reviewer.
