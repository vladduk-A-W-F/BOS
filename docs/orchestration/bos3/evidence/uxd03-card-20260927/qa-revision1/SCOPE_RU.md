# B30-UXD03-CARD-QA: границы подготовки

Статус: `PREPARED_NOT_EXECUTED`. Это новый узкий presentation-delta harness,
а не проверка приложения, прав, API, runtime или готовности.

## Основа

- Контракт: `D:/3/BOSDev/qa-scratch/bos3-uxd03-prep-20260927/UXD03_CONTRACT_RU.md`.
- SHA-256 контракта:
  `0a8f0f64cc566db6d855d37d7905a7fa98be682a37527d7ea59a53355de7735e`.
- Финальный авторский source: `C:/Users/user/.codex/worktrees/bos3-product-design/repo`,
  чистый commit `4999f7af9387488386729db02423460d9678bedf`.
- SHA-256 `frontend/boss_app_source.html`:
  `62e31d8f65879179d2b60124312c58fd848a3a252ef58737551adec3e57cc7fb`.
- Авторский отчёт: `docs/design/evidence-uxd03-20260927/AUTHOR_REPORT_RU.md`,
  SHA-256 `e931702f021e5cc0ccd09a6a6d6d4bd1a5588184b15ca1dbe1dab83788bd40b6`.

Этот source не принят этим документом: независимый reviewer
`bos3_candidate_review` проверяет author delta отдельно. Перед исполнением
нужны его verdict и отдельный root GO.

## Реальная зависимость автора и extraction

Точный helper автора: `c01TaskCardFacts(task, employees=[], departments=[])`.
Его result ровно:

```js
{
  orderLabel: string,
  assigneeDepartment: string,
  businessBranch: string,
  handoffLabel: string,
  recipientId: positiveInteger | null,
  recipientDepartment: string | null
}
```

Его реальные pure dependencies: `c01Id`, `c01HandoffShape`, `c01Object`,
`c01Display`, `c01Date`, `c01SourceRefs`. Никаких production markers или
нового API author не обязан добавлять ради QA. Harness структурно разбирает
полный source через уже включённый `assets/babel.js`, извлекает ровно эти
top-level declarations по AST и исполняет только их во VM с fixtures в памяти.
Он не загружает frontend, React, DOM, storage, API, DB или сеть.

`order_id` с code показывает code и реальный ID; пустой code даёт `№ID`;
null ID не выводит осиротевший code. Валидный `sent/current` с совпавшим
recipient/assignee даёт «Призначення чинне». `superseded/current=false` даёт
«Попереднє призначення». `current=true` с иным recipient, `sent/current=false`
или `superseded/current=true` дают только «Чинність призначення не
підтверджено» — не waiting, не acceptance и не «в работе». Неполная или
неизвестная schema не показывает recipient. `done`/archive не меняют смысл
валидного handoff; текущий статус Task остаётся отдельным фактом карточки.

## Будущие bounded проверки

`uxd03_card_test.cjs` после exact reviewer-approved source проверяет только
fixtures в памяти: null/legacy, unknown schema, recipient mismatch,
superseded, done Task, long Unicode order code и fallback order ID. Для
валидного handoff fixture содержит все поля, требуемые фактическим
`c01HandoffShape`. Harness также проверяет, что inputs не мутированы и result
содержит только presentation whitelist. Он не читает старые lessons,
fixture/progress, department membership, acceptance, HR/finance/history данные
и не утверждает policy/security boundary.

Проверка имеет собственный ярлык `NEW_PRESENTATION_DELTA`. Исторические
QA-лимиты остаются `SAME-PROBLEM`: этот harness не сбрасывает caps и не даёт
разрешения повторить progress, fixture, membership, browser, DB, network или
application suites.

## До исполнения

Требуются: (1) чистый commit и SHA-256 полного source, (2) независимый
reviewer verdict по helper и harness, (3) отдельный root GO на одну попытку.
До этого Node, imports, compile, build и app команды не запускаются.

## Сохранённый начальный draft

Первый prep draft (`SCOPE_RU.md` SHA
`e34ac02f63ce20f0d3f28f81ae46a96067029250daa1fdaa48b53053cf58a0b4`,
oracle SHA `ab5ca4360a4a42303028ad5c9413969ea79dbe95630309e7e9acb4609cd230eb`)
не исполнялся. Он ожидал заранее не согласованные markers и
`c01QueueCardFacts`; после точного author source заменён, а не выдан за
результат. Эта ревизия адаптирует oracle к фактическим declarations и не
изменяет production API ради PASS.
