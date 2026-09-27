# B30-UXD03-CARD — авторский отчёт

Статус: **AUTHOR_COMPLETE_REVIEW_PENDING**. Автор не выполняет независимое ревью и не принимает собственный результат. Следующий получатель — `bos3_candidate_review`, затем отдельно допущенный QA и единственный canonical root.

## Версия и границы

- Base commit: `e710eb568717dfe3ede945feb899f030bd5ad1ab`.
- Рабочая ветка: `codex/bos3-uxd03-cards-20260927`.
- Result commit — единственный коммит этой карточки, содержащий настоящий отчёт. Полный result SHA сообщается в финальной передаче после создания коммита; файл внутри коммита не содержит собственного циклического SHA. Хеши четырёх изменённых продуктовых файлов зафиксированы в `CHANGED_FILES.json`.
- Принятый контракт: `D:/3/BOSDev/qa-scratch/bos3-uxd03-prep-20260927/UXD03_CONTRACT_RU.md`, SHA-256 `0a8f0f64cc566db6d855d37d7905a7fa98be682a37527d7ea59a53355de7735e`.
- Классификация поручения: `NEW_PRESENTATION_DELTA_EXISTING_TASK_LIST_FACTS`. Она разрешает указанный presentation delta и одну штатную build generation, не прежние или новые продуктовые тесты.
- Исходное дерево проверено чистым; HEAD и ветка совпадали с поручением. Backend, model, policy, routes, fixtures, training harness, DB, runtime и общая оболочка не изменялись.

## Что изменено

В существующей очереди `Tasks` появились код и ID текущего заказа, краткий факт последней передачи, ID исторического получателя и снимок его отдела. Null order не превращается в фиктивную связь: подпись говорит только об отсутствии **текущего** заказа. Null/undefined handoff даёт «Відомостей про передачу немає» без утверждения, что передач никогда не было, и без строк получателя.

Для актуального назначения нужны одновременно `state=sent`, `current=true` и совпадение `recipient.employee_id` с текущим `assignee_id`. `state=superseded/current=false` подписан «Попереднє призначення». Противоречивые признаки дают «Чинність призначення не підтверджено». Нераспознанный handoff не получает выдуманных деталей. Основная существующая list validation сохранена; защитные ветви helper не ослабляют её. `current` не зависит от done/archive и не означает принятия, ожидания или выполнения работы.

Показаны отдельно:

1. «Поточний відділ виконавця» — связь текущего assignee с `Employee.branch` в уже прочитанном справочнике и дереве `type=department`.
2. «Відділ на момент передачі» — исторический снимок `handoff.recipient.department` с его ID.
3. «Початкова бізнес-філія» — `Task.branch_name`.

Если текущий отдел не сопоставлен в доступных справочниках, подпись сообщает об этом, не подставляя бизнес-филию или исторический отдел. Имя нынешнего исполнителя не копируется в исторического получателя.

Кнопка «Відкрити доручення — джерела й історія» вызывает прежний `open(t,'view')`. Она не обещает нового прямого перехода к заказу. Title, handoff/edit/archive/restore, проверки возможностей, lifecycle, повторные чтения, отзыв доступа, закрытие и возврат фокуса не менялись. Новых запросов, кэшей, хранилищ или действий нет.

Карточки используют текущую auto-fit сетку, светлые токены и семантические `dl/dt/dd`. Статус и серверная просрочка подписаны текстом; архив указан отдельно. Длинные имена/коды и основная кнопка переносятся; нет фиксированной высоты или обрезания. Scoped CSS задаёт кнопкам минимум 44 px, включая существующий inline minHeight компонента Button. Глобальный Button не изменён; полный ряд основной кнопки задаётся через передаваемый data attribute. Существующий focus-visible и reduced motion не переопределялись. Реальная адаптивность и клавиатура пока **NOT_RUN**.

## Данные, которые карточка не выводит

`history`, `result`, `expected_result`, `reason`, `source_refs`, sender/user IDs и роли, документы, финансовые поля, контакты, KPI и зарплаты не добавлены в отображение. Helper возвращает только шесть presentation-полей, без spread исходного Task/handoff/Employee. Значения выводятся обычным React text; raw HTML отсутствует.

Это whitelist отображения. Исходная Task list projection по-прежнему содержит result и полный разрешённый handoff; данная карточка не создаёт новую серверную границу секретности и не доказывает безопасность ролей.

## Проверки и фактический запуск

Единственный продуктовый запуск этой карточки — штатная генерация:

```text
C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe scripts/build_frontend.cjs
native exit: 0
stdout: JSX compiled; local script assets wired.
stderr: empty
```

`BUILD.json` фиксирует argv, cwd, начало/окончание, native exit, SHA-256 входов/выходов и attempt=1. `BUILD.stdout.log` и `BUILD.stderr.log` сохранены как исходные байты процесса. Автоматического повтора не было. Генератор лишь читает существующий content registry; training flow/harness не запускался и не менялся.

Автор прочитал diff, проверил `git diff --check` и допустимые пути перед commit. Это контроль пакета, не product QA. При read-only поиске обнаружено отсутствие корневого package.json; сборка использует существующий `scripts/build_frontend.cjs` и bundled Node/Babel, установка зависимостей не выполнялась.

При подготовке Git-пакета стандартный ignore не добавил два `.log`; они включены явно по двум точным путям. Staged whitespace check затем выявил CRLF в двух новых JSON evidence; только эти metadata-файлы нормализованы в LF. Исходные stdout/stderr сохранены без преобразования. Это исправления упаковки перед первым commit, без повторной сборки или продуктовых проверок.

**NOT_RUN:** unit/targeted tests, browser, screenshots, HTTP/network, runtime refresh, DB/seed/reset, migrations, training/payment/full/PG/E2E, cross-role execution, 390/768/1440/200% layout, клавиатура, возврат фокуса и stale/denied динамика. Ни один из этих пропусков не объявляется PASS. Субагенты не создавались. Runtime pin и readiness не менялись.

## Testable display helper и предлагаемые случаи

`c01TaskCardFacts(task, employees=[], departments=[])` — синхронная функция представления без I/O, времени, storage, DOM, capability lookup или мутации входов. Использует существующие чистые `c01Id` и `c01HandoffShape` (с их валидаторами). При последующем допуске harness должен извлекать точный helper и его реальные зависимости из source, не переписывать реализацию и не загружать приложение целиком. **Harness в этой карточке не написан и не запускался.**

Точный набор declarations для extraction: `function c01TaskCardFacts`, `const c01Id`, `function c01HandoffShape`, `function c01Object`, `function c01Display`, `function c01Date`, `function c01SourceRefs`. `c01Date` проверяет переданную ISO-дату через Date, не читает текущие часы. Дополнительных module globals, React или BOS_RUNTIME нет; helper не зависит от маркеров или предварительного имени QA.

Форма результата: `{orderLabel: string, assigneeDepartment: string, businessBranch: string, handoffLabel: string, recipientId: positiveInteger|null, recipientDepartment: string|null}`. Вход task — существующая list row, employees — уже прочитанные rows с `id/branch`, departments — уже нормализованные `c01Departments` элементы `{id,name}` только `type=department`. Для валидного handoff fixtures нужны настоящие поля схемы, включая sender/recipient, previous_assignee, expected_result, deadline, as_of и source_refs: shape validator использует их, но helper не возвращает их. Противоречие current=true/recipient mismatch всегда даёт неподтверждённую актуальность, не accepted/waiting.

| Предлагаемый случай | Проверяемый результат после отдельного допуска |
|---|---|
| order ID + code; пустой code; null ID со старым code | Код и реальный №; fallback №; отсутствие текущей связи без вывода осиротевшего кода. |
| handoff null и undefined/legacy | Только отсутствие сведений, recipientId/recipientDepartment=null. |
| sent/current=true, тот же assignee | «Призначення чинне», точный recipient ID и исторический отдел. |
| superseded/current=false, иной assignee; а также возврат к прежнему assignee | В обоих случаях «Попереднє призначення»; current не выводится из совпадения ID само по себе. |
| sent/current=true с другим assignee; superseded/current=true; sent/current=false | «Чинність призначення не підтверджено», без принятия/ожидания. |
| Неполный/неверной схемы handoff | Helper не выводит получателя; отдельная существующая list validation по-прежнему отвергает malformed row. |
| done/archive с валидным current handoff | Текст назначения сохраняется, статус/архив Task показан отдельно; не создаётся состояние работы или waiting. |
| Три разные филии/отдела; branch type не department; неизвестный assignee | Каждая подпись использует только свой источник; неизвестный текущий отдел не подменяется снимком передачи. |
| Null deadline/priority/assignee и длинные строки | Честные fallback подписи, нет искусственного срока/приоритета/имени; layout проверяется отдельно. |
| Строки с HTML-подобным содержимым; чувствительные canary поля | React отображает текст; whitelist результата helper и карточка не включают секретные canary значения/объекты. |
| Контракт вызовов и mutable inputs | Helper не меняет Task/directories, не выполняет запросы и возвращает ровно presentation whitelist; open/actions остаются прежними. |

Будущие динамические/визуальные/role cases требуют отдельной классификации и независимого review harness, с сохранением исторических лимитов. Этот список не выдаёт такой допуск и не является результатами тестов.

## Выход

Editable: `frontend/boss_app_source.html` (локальный helper и карточка Tasks), `frontend/bos_design.css` (только scoped card styles). Generated-only: `frontend/boss_app_html.html`, `assets/app.js`. Evidence-only: настоящий каталог. Полные изменённые product file hashes — `CHANGED_FILES.json`.

Передать точный result commit независимому `bos3_candidate_review`. UXD03 waiting-семантика и полный readiness остаются за пределами этой карточки. Commit/build не означают acceptance или runtime delivery; `TECHNICAL_READY`, `PILOT_ALLOWED`, `MVP` не изменяются.
