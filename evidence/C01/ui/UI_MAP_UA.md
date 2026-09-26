# C01: межі UI та наявні входи

База: canonical frontend f00fe5165592b9e8a8a71fda7d16c2f70ba61620a94a864c7ef3eb4dc1635c60. Робота тільки в tmp/c01_ui_candidate. Повний C01_IMPLEMENTATION_CONTRACT_UA прочитано; API звірено з автором через C01_WIRE_UI_UA.md.

| Вхід | Початковий розрив | Узгоджена зміна |
|---|---|---|
| Tasks create | Raw POST, assignee рядок, необов’язковий deadline | ControlledTask, explicit Employee ID, server as_of, preview/confirm |
| Tasks edit | Raw PATCH title/category/name/date | Одна форма, touched fields, reason; omitted legacy NULL не заповнюються |
| Tasks status/priority | Raw PATCH, клієнтський overdue як persisted status | Та сама форма з явним preset; серверний diff, result для нової completion |
| Tasks remove | Hard DELETE | Окремий archive update з reason; архів та restore з тими самими ID |
| Topbar | Окремий raw POST/name picker | ControlledTask плюс глобальна ID-only pending recovery панель |
| Procurement | Старий ControlledTask create | Спільна форма зі збереженим request_code та defaultEmployee ID |
| Assistant / JSON | Старий ControlledTask; довільний non-ERP JSON | Строгий Task JSON parser без повторних/невідомих полів; спільна форма |
| Read-only Tasks | Окремий обмежений список без історії | Той самий список, view/history/archive без write-кнопок |
| NavBar/Home/Inspector | Client date fallback та legacy assignee | Тільки Task read aliases: server is_overdue, assignee_name, active archive filter |

Погоджена root межа: Task-only read зміни в BoSHome/Inspector/NavBar дозволені §8; усі ERP/B02/B03 actions/dialogs/не-Task таблиці побайтово збережені. Нового дизайну всього продукту немає.

Єдине сховище pending у поточній вкладці: proposal_id, create_task/update_task, task_id|null, user_id. Воно не зберігає причину, результат, текст або джерельні snapshots. Перед confirm storage має пройти; generic409/5xx/network не очищують ID. Read GET pending/expired не є доказом невиконання; тільки receipt або locked proposal_stale/proposal_expired дозволяють закрити цей pending. Новій сесії доступний read, але не old proposal POST.

Baseline actual commit closure при моделюванні втраченої відповіді стирав proposal. BASELINE_RED.json містить цей виконаний red і source inventory 5 Tasks raw writers, Topbar raw POST, status overwrite. Подальші UI_PROOF.json виконують фактичні витягнуті JS-функції з контрольованим transport/storage. Це не browser, не API/DB acceptance. A11 не повторювався.
