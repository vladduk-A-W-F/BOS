# UXD02-MONITOR-QA: підготовка oracle

Підготовлено один hash-bound Node runner і scope/manifest для exact source
`0f9e94bee39ad7340b47ce762f4ee077726a6ea3`. Жодного Node, Babel parser,
VM, build, browser, HTTP, DB, runtime або application import не виконувалось
під час цієї підготовки.

Runner не дублює predicates. Він знайде через Babel AST і виконає у порожньому
VM exact declaration slices `purchaseRemaining`, `b03Positive`, `b03OpenLine`,
`monitorRows`, `b03FindRecord`, `homeSelectionVisible`; fixtures тільки в
пам'яті. AST частина перевіряє межі selection/readOnly, які не можна чесно
підтвердити pure helper викликом.

До review виправлено один harness-only cross-realm ризик: порожній масив із
Node VM перевіряється через `Array.isArray` і `length`, а не strict deep
equality з host-array. Predicates, fixtures, expected IDs, source pin і
product source не змінювалися.

AST assertions також фіксують саме `null` очистку selection/origin у publish
та всі чотири existing manual-review conditions (`readOnly`, write, current,
`needs_review`), а не лише наявність довільного виклику чи identifier.

Очікуваний evidence coverage обмежений трьома metric lists та presentation
guards. Browser focus/ESC/dialog, Policy, actual document fetch і trace
lifecycle в React не покриті та не повинні інтерпретуватися як PASS.

Перед єдиним run1 потрібні independent review exact scratch files і окреме
root GO. Попередні UXD01 та control-manifest спроби не належать цій новій
класифікації і не скидають/не витрачають її cap.
