# UXD03-WAIT-01: проект требует уточнения

27.09.2026. Proposal author: observer `/root/readiness_requirements`.
Независимый reviewer: `/root/bos3_candidate_review`.
Source: clean `e710eb568717dfe3ede945feb899f030bd5ad1ab`.
Вход UXD03_WAIT_PROPOSAL_E710.json, SHA-256
`1a8a6c87c364799128cb048b280aa85b9fe3855c600053b4a64c31f5020c2768`.

Вердикт: **REVISE_BEFORE_IMPLEMENTATION_CONTRACT**.
Направление orthogonal waiting обосновано, но контракт не завершён.
Это статические findings проекта, не наблюдавшийся сбой приложения.

1. **P1: права участника и видимость причины.** Task scope зависит от
   накопленных business-source refs (tasks/queries.py:44), а list/detail
   делят одну проекцию (55), history возвращает reason (tasks/history.py:21).
   Active employee/user/department не доказывает доступ участника к
   источникам, в отличие от handoff (tasks/handoffs.py:46). Требуется
   выбор source-authorized внутреннего участника либо dependency reference,
   повторная проверка preview/confirm/replay/status/access revision и точная
   role/list/detail/history матрица name/department/reason. Free-text reason
   нельзя автоматически раскрыть всем читателям списка; определить
   непустую причину и границы чувствительных данных.
2. **P1: lifecycle и блокировки.** Generic update меняет assignee/status/
   deadline/order/archive и прочие поля (tasks/commands.py:18). Нужна
   единая таблица разрешённых изменений и общий wait guard для update,
   handoff, archive, completion/reopen, start/end, proposal status/confirm.
   Current confirm lock routing знает только существующие actions
   (operations/service.py:139); waiting отсутствует в fingerprint/history.
   Сохранить порядок transaction.atomic -> write_lock -> task lock ->
   все необходимые employee rows в стабильном порядке. Включить wait
   в fingerprint, CAS/replay, audit, dispatch и stale conflict checks.
3. **P1: деактивация и выход из ожидания.** FK PROTECT не предотвращает
   архивирование, отключение user, смену отдела/прав. Start/replay требует
   active/source-authorized participant. End должен оставаться доступным
   уполномоченному нынешнему actor даже после деактивации/потери доступа
   участника, без auto-clear. Определить stale исход start/end proposals
   и сохраняемый audit snapshot первоначального участника/причины.

## Граница решения

Нужен исправленный точный контракт, затем explicit owner/integrator
решение о persistent orthogonal fields и paired-null DB constraint.
Новая migration-backed карточка не назначена. Source-only owner-local
update с сохранением bytes БД не разрешает миграцию. Текущая UI-card
остаётся отдельной и не заменяет полное UXD03.

Executions/code edits/DB/runtime changes: 0. Readiness false.
Следующий получатель findings: автор через существующего observer;
после исправления требуется независимое review, не автоматический PASS.
