# Независимая проверка настройки постоянного контроля BoS

- Проверено: 2026-09-27T14:04:33Z.
- Проверяющий: `/root/projectwide_control_review`.
- Режим: read-only; тесты, браузер, HTTP, runtime и изменения канонического дерева не выполнялись.

## Verdict: CHANGES_REQUESTED

Подготовленные документы задают корректный целевой контур, но действующая automation ещё не приведена к нему. Поэтому постоянный контроль всего проекта нельзя считать включённым до обновления **существующей** automation `automation` и повторной точной сверки сохранённой конфигурации.

## Что принято в подготовленных документах

1. Охват явно включает backend/ERP/CRM, модели и контракты данных, frontend/UX, вход/права, обучение/прогресс, synthetic QA, документы/PDF, release-пакеты, локальную доставку, инструменты и межотдельские каналы. Отдельный Sites/«Опора» и исторические пакеты отделены от BoS runtime.
2. Сохранён один интегратор `01a0dd56-ca2d-79c0-b159-bde80074a026`; автор не принимает собственную работу. Цепочка передачи требует карточку, отдельную копию, независимый review, разрешённую QA, evidence, последовательную интеграцию и подтверждение потребителя результата.
3. Протокол требует реальные base/result/review/integrated/runtime pins, сохранение незавершённых worktree, запрет слепых reset/force-rebase, отсутствие ACK-циклов, ложных PASS и повторов успешных проверок без новой причины.
4. Подготовленный prompt сохраняет 15-минутный цикл и cutoff 04.10.2026 23:59 Europe/Berlin. Он учитывает актуальные `owner_local_update_policy` и `light_preview_delivery_permission`: обычный reviewed owner-local update не ждёт нового запроса, но текущее окно остаётся ограниченным одной доставкой и entry-check без reset/seed/migrate/уроков/записей ERP/CRM/автоповторов.
5. Протокол правильно устанавливает: промежуточная установка dev.3 не останавливает постоянный контроль; после cutoff остаются чтение, итог и пауза automation. Отдельные caps, доступы, данные и readiness остаются прежними.

## Обязательное исправление

**F1 — фактический heartbeat устарел и противоречит готовым документам.**

Основание:

- В `C:/Users/user/.codex/automations/automation/automation.toml` сохранены правильные id `automation`, target `01a0dd56-ca2d-79c0-b159-bde80074a026`, ACTIVE и интервал 15 минут.
- Но его текущий prompt всё ещё говорит, что вопрос о local update/restart и entry-check «остаётся нерешённым», хотя канонический `CONTROL_STATE.json` фиксирует `light_preview_delivery_permission.status=AUTHORIZED_ONE_SHOT`, `earlier_pending_resolved=true` и `owner_local_update_policy.owner_quote=ВСЕГДА ОБНОВЛЯТЬ И МЕНЯТЬ`.
- Тот же сохранённый prompt предписывает после состоявшейся доставки «приостановить automation до новых указаний». Это противоречит новому прямому поручению о постоянном контроле и `CONTROL_PROTOCOL_RU.md`, где явно сказано не останавливать контроль после промежуточной установки dev.3.
- В фактическом prompt также отсутствует добавленный раздел о контроле **всех** согласованных направлений и правила передачи отзывов/коммитов после нового поручения владельца.

Нужное действие: владелец текущего tracker обновляет только существующую automation `automation` подготовленным `AUTOMATION_PROMPT_RU.md`, не создавая новый таймер, затем повторно читает TOML и подтверждает exact prompt, id, target, ACTIVE, 15 минут и cutoff. До этого automation-карточка остаётся In progress, а не Completed.

## Сверенные актуальные pins и границы

- Canonical integration: `C:/Users/user/.codex/worktrees/bos-consolidation-plan/repo`, branch `codex/bos3-prerelease-20260927`.
- Sole integrator: `01a0dd56-ca2d-79c0-b159-bde80074a026`.
- Current delivery candidate: `f55a15de4006d10c0d7c65f8a2ca8499fbb99819`.
- Delivery state: `AUTHORIZED_ONE_SHOT`; next card `B30-PREVIEW-DELIVERY` is `IN_PROGRESS`.
- Current runtime pin in the reviewed state is still dev.1 `33d7d387aa582c04339a91ae94361948ea67904c`; this review does not claim a completed runtime transition.
- Readiness remains `technical_ready=false`, `pilot_allowed=false`, `mvp=false`.
- Canonical worktree has in-progress owner-local delivery evidence and a modified `CONTROL_STATE.json`; it was intentionally not edited or treated as a completed runtime receipt in this review.

## SHA-256 reviewed files

| File | SHA-256 |
|---|---|
| `CONTROL_PROTOCOL_RU.md` | `73935537E56D5E104EDF8EE0BF425F3EBAF135C4B3CF35BBA03C66C97A9B76A1` |
| `AUTOMATION_PROMPT_RU.md` | `6784946FB67A032B43DF29A5C506548A49C6AC8825AE045F77A50CB1CF1E157C` |

