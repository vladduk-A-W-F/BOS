# B30-INVOICE-CURRENCY: независимое static review

27.09.2026. Author: existing writer `01a0be9f-b413-7822-9f93-16ba69f4f00f`.
Reviewer: `/root/bos3_candidate_review`. Integrator: root.
Source: `9f7d50cc39c6d1fdfe19025e1789d54a2176535d`, declared base `d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`.
Workspace: `C:/Users/user/.codex/worktrees/bos3-task-card-pack/repo`, branch `codex/bos3-invoice-currency-20260927`.

## Раздельные вердикты

- Code: `ACCEPT_SCOPED_STATIC_CODE`. Только invoices добавлены в sorted currency universe; actual Decimal-формулы, `@exact`, сортировка, EUR fallback, права, API и действия сохранены.
- Oracle: `ACCEPT_SCOPED_UNRUN_PURE_SNAPSHOT_ORACLE`. SimpleTestCase проверяет точную invoice-only USD строку с receivable `125.50`, paid `24.50` и нулевыми остальными показателями; второй случай сохраняет EUR fallback. Task queries замещены. Тест не запускался.
- Evidence: `REVISE_BEFORE_EVIDENCE_ACCEPTANCE`. В AUTHOR_REPORT_RU.md literal `$base` и управляющие ESC/form-feed/backspace вместо путей и идентификаторов. Требуется читабельный точный отчёт, `tests_not_run=true`; отсутствующий raw не создавать задним числом.
- Предложение `manage.py test ... --keepdb` не считается разрешённым и недостаточно строго обеспечивает отсутствие доступа к существующей БД. Нужен отдельный изолированный runner review/classification без keepdb.

## Передача и следующий шаг

Root один раз передал findings прежнему автору через native send_message_to_thread. Возврат не подтверждён за 25 секунд; отправка не повторяется, другой автор не назначен. Разрешён отдельный evidence repair commit без amend исходного 9f7; code и test не менять. Возможна корректировка только предложенной команды в MANIFEST.json с pending review, без запуска.

Независимая подготовка B30-INVOICE-CURRENCY-QA назначена существующему `/root/bos3_crm_impl`, allowlist только `D:/3/BOSDev/qa-scratch/bos3-invoice-currency-20260927/`. Source pin тот же 9f7. До review `/root/start_overview_review` и root classification никаких tests/imports/Django setup/DB/network/browser/build/runtime. Новый ID не сбрасывает старые лимиты; applicability к fixture/progress/payment ограничениям проверяется отдельно.

Result пока не интегрирован и не доставлен. Установленный dev.7/d8, readiness false и старые owner questions сохранены. Native completion metadata автора остаётся UNCONFIRMED; доступный Git artifact не подменяет подтверждение доставки findings.

## Последующее исправление и подтверждение

Reviewer принял exact evidence repair `906f678a4c8f045deb03489f6566af66086e9120`: `ACCEPT_SCOPED_EVIDENCE_REPAIR`. Изменены только AUTHOR_REPORT_RU.md и MANIFEST.json; code/test идентичны9f7. Команда keepdb отозвана, tests_not_run=true и executions0 сохранены. Root git parent read подтвердил9f7 -> d8; native turn01a0e47a-b8ca-7613-b45d-7e6d2f2154a9 completed/idle подтвердил фактическое исправление. Прежний UNCONFIRMED delivery findings снят этим новым результатом, не повторной отправкой.

QA подготовку завершил как PREPARATION_INCOMPLETE_NO_EXECUTION: транзитивный import graph и @exact не подтверждены для no-DB isolated runner. Provisional protocol на D заменён immediate STOP. Исполнений0, QA PASS не заявлен. Продукт не интегрирован/не доставлен.

Owner request о переносе BoS на D подтверждён в native observer userMessage01a0e433-6fce-75e3-a26d-04dc212f703b. Новые C write tasks не выдаются. Запрос explicit writer quiescence получил native ошибку Cannot steer without active turn id, не считается декларацией. Source906 и nearest root documentary checkpoint сохраняются; storage prerequisites отдельны от качества продукта.
# Documentary checkpoint acceptance

27.09.2026, independent bos3_candidate_review: ACCEPT_SCOPED_DOCUMENTARY_CHECKPOINT.
ACTIVE historical states explicitly separated from current queue; CONTROL/TEAM agree.
Automation original update confirmed; invoice9f7/906 static accepted, not integrated.
Guarded QA NOT_READY_FOR_RUN, same D-only author repairing guards/pins/scope, executions0.
Fresh catalog doctor exit0 only proves tool presence, not historical/new-message delivery.
Storage window awaiting owner answer; root copy/switch/runtime actions0. Runtime d8/dev7
and all readiness flags unchanged. No new execution permission follows from this review.
