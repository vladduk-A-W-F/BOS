# Независимое review CRM stale detail source, round 2

Карточка `B30-CRM-STALE-AND-PROPOSAL-REVIEW-20260930`; предмет `B30-UXD07-CRM-STALE-DETAIL-20260930`. Round 1 (`CHANGES_REQUIRED_SOURCE_SCOPE`, SHA-256 `7b4a9de4b887fe00ade8e0c34b27330615571716063bcbec1c1e7ca2e544819e`) отдельно сохранён root. В этом verdict рассмотрен только новый R2: неизменный dev9 baseline `frontend/boss_app_source.html` SHA-256 `145bcaa359138d1046e1aed88540c5975409596531af8ce9d873abe0a3c146c9`, авторский файл SHA-256 `fc82733a97c3532cd8ea45ec9dfbfbd96d9274054c83d512b7fa8d40f8772384`, raw diff SHA-256 `0ce6bd200417774c447931422b7fdcac3d5a1b43f8a61efc96ace3ad5c7e06eb`, `IMPLEMENTATION_RU.md` SHA-256 `29458be7283d9d6508a95ffe075c82c3213e179bd51d43fb8f8e67127e9cbe1a`, `RESULT_MANIFEST.json` SHA-256 `d85e721841b4b8572ec355aa40095617d17a890d0af6ba712d47c8bddb8c524c`. Источник dev9 HEAD `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`; его и canonical baseline файл ранее сверили по SHA. Автор и reviewer разделены.

## Вердикт

**ACCEPT_SOURCE_STATIC_R2.** В полном diff (только `CRMProposal` и `CRMWorkspace`) не найден блокер для узкой source-правки UXD07. Принятие относится к тексту исходника и статическому поведению, не к сборке, browser/role QA, исполнению, доставке или готовности. Архивировать reviewed source/patch как неактивное evidence можно с этим точным SHA; canonical frontend и generated assets в этом review не изменялись.

## Проверенное поведение

- Каждый `loadDetail(id)` создаёт новое поколение; success, error и завершение ожидания применяются лишь при совпадении поколения, `bosHttpScope()` и живого компонента (`:5527-5533`). При кликах A→B и ответах B→A или A→B поздний A не может вернуть карточку, ошибку или pending state. Ответ с чужим `id` отклоняется.
- Новый выбор сразу скрывает прежнюю редактируемую карточку, отмечает B по `detailId` и показывает loading (`:5529,:5542`); error текущего B оставляет карточку пустой. `bos:data-changed`, `bos:session-ended` и unmount инвалидируют ожидающий GET (`:5536`). Это соответствует исходному P2 finding о достоверности карточки.
- Замечание round 1 по позднему auto-open исправлено. `chooseDetail` отдельно увеличивает `userSelection` (`:5535`). `preview` снимает номер, поколение и scope **до** `opFetch`, поэтому поздние `existing`/`no_change`, proposal и ошибка не применяются после нового выбора или изменения контекста (`:5539`). `CRMProposal` вызывает `onConfirmStart` до своего `opFetch` (`:5506`); `confirmed` сверяет этот номер с исходным proposal и текущим выбором после загрузки списка (`:5540`). Если B выбран пока confirm A в полёте, собственное `bos:data-changed` очищает detail generation, но не `userSelection`, и receipt A не может автоматически открыть A. Если B выбран уже во время `load()`, generation также блокирует auto-open.
- Контракты команд и backend не затронуты. Независимый `git diff --no-index --numstat` показал 23 добавленные/2 удалённые строки, exit `1` (различие); `git diff --no-index --check` дал пустой вывод, exit `1` (различие), whitespace findings `0`.

## Предел

Это доказательство по исходнику, `executions=0`. App import, Node, тесты, сборка, HTTP, browser, runtime, DB/media и generated asset verification не запускались. Сценарии с отложенными ответами, role UX, узкими viewport и клавиатурой остаются `NOT_RUN` до отдельного допуска. Исходная проблема GET и замечание round 1 статически закрыты в R2; это не означает фактическую доставку dev9 или production. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`; исторические лимиты не меняются.
