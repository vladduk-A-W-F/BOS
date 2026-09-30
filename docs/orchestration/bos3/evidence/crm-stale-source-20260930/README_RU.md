# CRM: неактивный исходный кандидат

Карточка `B30-UXD07-CRM-STALE-DETAIL-20260930`, продолжение прежнего подтверждённого P2: поздний ответ по сделке A мог заменить выбранную позже B. Автор `/root/crm_stale_resume`; независимый reviewer `/root/crm_stale_review`; sole integrator root. Requested Sol/medium и Sol/high соответственно, observed UNCONFIRMED. Исходная находка и её независимый verdict сохранены отдельно от review исправления.

## Граница пакета

Первая версия `ef7206b5` **не принята**: `SOURCE_REVIEW_ROUND1_RU.md`, verdict `CHANGES_REQUIRED_SOURCE_SCOPE`, SHA-256 `7b4a9de4b887fe00ade8e0c34b27330615571716063bcbec1c1e7ca2e544819e`. GET A→B защищён, но поздний preview/confirm ещё может переиграть новый пользовательский выбор. Файлы этой версии сохранены как история review, не как принятая правка. Тот же автор продолжает repair по прежней карточке; новый exact candidate и отдельный verdict обязательны.

Repair завершена тем же автором: актуальная версия находится в **`round2/`**, HTML SHA-256 `fc82733a97c3532cd8ea45ec9dfbfbd96d9274054c83d512b7fa8d40f8772384`. Независимый `round2/SOURCE_REVIEW_RU.md` SHA-256 `58932676f44dbeb2897e8c168829963972a404861198fffdd60b3f1ccb7f056b`: **ACCEPT_SOURCE_STATIC_R2**. Отдельный userSelection защищает от позднего программного открытия после preview/confirm; lifecycle generation сохранён. Верхнеуровневые author files остаются неизменной историей R1. Принимать пакет к публикации можно только после `PACKAGE_REVIEW_RU.md`.

`boss_app_source.candidate.html.txt` содержит точные авторские HTML-байты, но хранится как текст вне сборочного/runtime пути. `CRM_AUTHOR_RAW.patch` является исходным diff с абсолютными историческими путями; его нельзя автоматически применять как переносимый patch. Кандидат не заменяет `frontend/boss_app_source.html` или generated assets. Исправление требует независимого source verdict, затем отдельно допустимых сборки, адресного QA и exact-version доставки. Исходный UI/backend contract preview/confirm не расширяется.

Baseline HTML SHA-256 `145bcaa359138d1046e1aed88540c5975409596531af8ce9d873abe0a3c146c9`; candidate SHA-256 `ef7206b5460af133fbfbbce94d6b98c96e8f910a1df48f077834c4d6bba0de76`. Docs base `c9053d6cdb206dbfc28e69dfb52b8d913c5fb119`; immutable dev9 `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`; product `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf` не изменён. SHA результата относится к отдельному исходнику, не к новому runtime commit. Commit/PR публикации фиксирует внешний `ROOT_PUBLICATION_RECEIPT.json`, чтобы не создавать self-referential SHA.

Сборка, tests, Node, browser, HTTP, app imports, DB/media, runtime и ресурсные probes: **NOT_RUN**, executions=0. Низкий запас ресурсов614MiB передан observer; новых probes или heavy jobs этот пакет не разрешает. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`; текущая доступность runtime UNCONFIRMED, dev9 NOT_DELIVERED. Приложение и сохранённые данные пакет не трогает. `.gitattributes` удерживает принятые байты без преобразования строк.

## UXD04: предложение, не допуск

Точные `ADMISSION_PROPOSAL.json` и `PROPOSAL_RU.md` сохранены с независимым `PROPOSAL_REVIEW_RU.md`: `PROPOSAL_ACCEPTABLE_WITH_PRE_EXECUTION_REFINEMENTS`. До возможного executable manifest нужны равенство recipient history.handoff и receipt.handoff с отдельной проверкой projection current/state; закреплённые различные исходный Task.result и expected_result с неизменностью Task.result после confirm/replay; same_session=true, тот же proposal_id и неизменные IDs/число ActionProposal. Accepted trace не проверялся повторно.

Никакой новый execution admission не создан. История P05/A09/A10/A11, fixture3/3, progress Node1/1, network/full/PG/E2E/browser/lifecycle/storage/diagnostic остаётся в canonical records. Смена ID, автора или версии не сбрасывает лимиты. Следующий владелец: root для отдельных допустимых build/QA/delivery scopes, reviewer для exact admission, владелец проекта для уже заданных блокирующих решений. Публикация этого архива не означает завершения полного плана или недельного контроля.
