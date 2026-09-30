# Ограниченная обработка отказа atomic replace

Root включает B30-DEV8-ATOMIC-RECEIPT-REPAIR в единственный D canonical от
39952be1eb2dc28dc7d218b49ed051d5ff610e20. Между source60f и этим docs HEAD
scripts/bos3_local.py не менялся. Runtime этим коммитом не обновляется.

Product allowlist: только atomic_json в scripts/bos3_local.py и новый
scripts/test_bos3_local_atomic.py. Source SHA256 6483cc03bb7ea8fbf4e15a4b52c881b14ef0d8005cd0b16bafdf6455fa4c79da;
test SHA256 8b953ad4bfe8430e4da8e2b81c59105be116ae4364caf0b5d006409159264a1c.
Сохранены atomic replacement и исходный временный файл: максимум три
попытки только для PermissionError winerror5/32/33, суммарная задержка150мс.
Постоянная ошибка поднимается, прямой overwrite/ACL/lifecycle retry не добавлен.

Автор bos3_channel_diagnosis; независимый reviewer start_overview_review.
REPAIR_ORACLE_DELTA_REVIEW_RU.md принимает точный исправленный oracle.
QA bos3_crm_impl выполнил один root-authorized standard-library запуск:
5/5, native0. REPAIR_QA_RESULT_REVIEW_RU.md принимает raw result scoped.
Повторов нет. Тест намеренно привязан к сохранённому D scratch source,
а не является переносимым тестом всего приложения или CI-обещанием.

MANIFEST.json и авторский отчёт сохраняют исторический статус UNRUN до QA;
последующие ROOT_QA_DECISION, run1 и result review задают фактический результат.
Conservative same-problem счётчик2/3: actual failed start + synthetic run.
Spent window1 start1/1 не открывается заново. Lifecycle/HTTP/browser/login/
уроки/ERP/CRM/progress не проверены, исторический держатель lock не доказан.

Текущая доступность UNCONFIRMED после failed dev8 start. Новый получатель
после независимой интеграционной проверки: packager для минимального кандидата,
затем отдельное exact-pin recovery decision. Подготовка recovery template
у того же автора отдельно, executions0. Все readiness false.
