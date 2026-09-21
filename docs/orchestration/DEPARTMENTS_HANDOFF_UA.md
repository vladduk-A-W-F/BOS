# Передавання існуючого доручення між підрозділами

`handoff_task` передає той самий `Task.id` через наявні `/api/operations/preview/` і `/api/operations/confirm/`. Це призначення отримувачу зі статусом `active` («передано»), а не особиста прийомка, accept або return.

Точний payload: `action`, `task_id`, `assignee_id`, `expected_result`, `deadline`, `reason`. ID є позитивними integer без boolean/coercion; очікуваний результат 3–2000, причина 3–1000 символів, deadline — ISO `YYYY-MM-DD` не раніше server `as_of`.

Сервер бере sender із поточного користувача. CEO може передати доступне доручення і чесно зберігається з nullable employee; manager може передати лише доручення, призначене його current linked Employee. Отримувач — active nonarchived Employee з active linked User, однією реальною роллю CEO/manager та `Employee.branch.type == department`. `Employee.department` не використовується для identity. `Task.branch`, result, created_at і source history не змінюються.

На preview, confirm та replay перевіряються всі накопичені source refs і стан sender/recipient. Proposal fingerprint охоплює task/history, employee/user/role/branch, source access state та `as_of`; дія використовує чинний write mutex, row locks, CAS receipt claim та одну транзакцію для Task/AuditEvent/receipt. Повтор same proposal повертає наявний receipt без нового audit. Later generic reassignment не робить старий expected result current.

Read DTO містить `handoff` тільки як latest handoff with `current`; history містить typed `handoff`. `department_id` для `/api/tasks/` — один strict positive ID і фільтрує лише current assignee Employee.branch type `department`; він не змінює source Policy або `Task.branch`.

Обмеження: немає нового queue/model/migration, немає personal accept/return, KPI або UI. Статуси TECHNICAL_READY та PILOT_ALLOWED лишаються false до незалежного review та окремого integration decision.
