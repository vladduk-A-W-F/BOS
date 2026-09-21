# REVIEW-BRANCH-RECONCILE

Пріоритет P1. Власник bos_architect. Статус READY_READ_ONLY. Залежності: немає; реалізація продукту не входить у цю картку.

## Проблема й доказ
PR1 `620aeab2010c6c8327ce46c25bb62435bcf7f9e4` і PR2 `abb8845f6563bafa806029ddc1e7c2cace09907c` розійшлися від `edd5227e666442d8324044559b6e8cf10eaf8be1` (PR2: +15/-18). У PR1 erp/migrations/0006_branch_links.py та у PR2 erp/migrations/0006_network_operations.py обидві залежать від 0005_source_corrections і додають Location.branch. PR1 також додає SalesOrder.branch, PR2 — fulfillment_location. У PR2 0007_request_timing залежить від його 0006. Звичайна merge migration сама по собі не усуває повторне AddField.

## Дозволені файли й наступний крок
Читання: обидва erp/migrations/*, erp/models.py, service/queries/policy, procurement migrations, frontend/boss_app_source.html, відповідні source consumers і orchestration реєстри.
Запис цієї картки: лише новий docs/orchestration/reconciliation/* звіт/картка та погоджені PLAN/STATE/QUEUE у виділеній review-гілці. Продуктові правки — окрема наступна картка з точним allowlist після діагнозу.
1. Перечитати remote heads і зберегти карту двох графів, полів і споживачів; не перемикати активний checkout.
2. За дозволеними наявними звітами з'ясувати застосованість міграцій; невідоме позначити UNKNOWN. Не читати реальні клієнтські дані і не підключатися до робочих БД.
3. Запропонувати сумісний шлях із збереженням історії та обох бізнес-семантик; не видаляти/переписувати застосовані міграції за припущенням.
4. Окремо звести черги: NETWORK-PLAN-CURRENCY уже scoped accepted у NETWORK_ACCEPTANCE_UA.md при f00a2faf; NETWORK-ACCEPT-PC більше не є автоматично runnable після workflow 3/3. Зберегти обидві лінії evidence і нові CORE картки, а не заміняти свіжу QUEUE старою.
5. Зафіксувати main divergence +56/-2 та дві власні CI-зміни main; reconcile main лише окремим наступним завданням, не merge зараз.

## Приймання
Незалежний reviewer підтверджує повний mapping колізій, один запропонований граф без подвійного поля, сумісність SalesOrder.branch/fulfillment_location, точні refs та окрему виконавчу картку. Ця картка приймає ПЛАН інтеграції, не її виконання. Фінальна runtime-перевірка графа — лише після окремої дозволеної реалізації.
Заборонено merge/force-push, міграції БД, product edits, full/PG/E2E reruns, production та зміну AGENTS. Ліміти з [checkpoint](../daily/2026-09-21.json) не скидаються.
