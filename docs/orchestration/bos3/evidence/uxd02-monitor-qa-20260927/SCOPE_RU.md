# UXD02-MONITOR-QA: межа pure helper та AST evidence

## Класифікація і пін

`NEW_THREE_METRIC_SELECTION_PREDICATES_AND_READONLY_PRESENTATION_NOT_LEARNING_PAYMENT_BROWSER_RETRY`.
Це нова isolated presentation/helper картка, `0/3` динамічних спроб.

- Target checkout: `C:/Users/user/.codex/worktrees/bos3-product-design/repo`.
- Target commit: `0f9e94bee39ad7340b47ce762f4ee077726a6ea3`.
- Target source: `frontend/boss_app_source.html`.
- Target source SHA-256:
  `145bcaa359138d1046e1aed88540c5975409596531af8ce9d873abe0a3c146c9`.
- Author report SHA-256:
  `55342b23e36e5136eb35e5a2c85407ca218a584f235d1ac0cdcabb37194aaff5`.
- Author manifest SHA-256:
  `1d3ab0b28225bdfd9a33ffc0552536b2783e3f3f20e405f16c127b6ff381b22b`.
- Author build receipt SHA-256:
  `bd78155e43f3cc9d1a458241d8369e27d9ab780e245bebf0e6b888bc317b3968`.

Перед майбутнім запуском runner вимагає чистий target checkout, exact HEAD і
SHA-256 source. Незбіг є STOP, не підставою змінити очікування.

## Що покриває oracle

1. Babel AST витягає незмінені real declarations `purchaseRemaining`,
   `b03Positive`, `b03OpenLine`, `monitorRows`, `b03FindRecord` і
   `homeSelectionVisible` з одного `text/babel` body. У порожньому Node VM
   запускаються тільки ці exact declaration slices та малі dependency stubs
   для не-monitor branches `homeSelectionVisible`; застосунок не імпортується.
2. `monitorRows` перевіряється на in-memory synthetic snapshot:
   order effective `open_quantity`, fallback `quantity-shipped`, відсутність
   status/confirmed фільтра, один row при кількох open lines, jobs `!= done`,
   quality positive quantity та OR quality/documents, same IDs/count, empty
   null/unknown keys і відсутність мутації input/row identity.
3. `homeSelectionVisible` перевіряється лише за його власним контрактом:
   monitor-list key/origin, unknown/mismatch rejection, generic list/metric
   with `monitorOrigin` rejection і visible/non-visible record IDs. Initial
   record kind/membership guard перевіряється AST у `inspectMonitorRecord`,
   бо саме цей handler виконує `monitorRows(...).some(...)` до `open`.
4. Narrow AST boundary: `DocViewer` default `readOnly=false` та manual review
   gate, `BoSInspector` forwarding `readOnly`, monitor inspector with
   `readOnly` and omitted `onAction`/`onNavigate`, `begin` monitor gate, та
   selection/origin clear на non-ready publish і trace handoff.

## Не покривається

Не доводяться browser focus/dialog/ESC, React state scheduling, visual layout,
HTTP, Policy/role enforcement, document fetch, OrderTrace lifecycle, backend,
DB, runtime, training, payment, learning, migration, full suite або historical
browser retries. Відсутність такого доказу не є PASS.

## Майбутній єдиний запуск

Лише після independent review `start_overview_review` та окремого root GO:

```text
C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe \
  D:/3/BOSDev/qa-scratch/bos3-uxd02-monitor-qa-20260927/uxd02_monitor_test.cjs \
  --source C:/Users/user/.codex/worktrees/bos3-product-design/repo/frontend/boss_app_source.html \
  --commit 0f9e94bee39ad7340b47ce762f4ee077726a6ea3 \
  --sha256 145bcaa359138d1046e1aed88540c5975409596531af8ce9d873abe0a3c146c9
```

Без automatic retry. Raw stdout/stderr/native exit/argv/pins мають піти до
нового `run1/`, не в author або canonical дерево.
