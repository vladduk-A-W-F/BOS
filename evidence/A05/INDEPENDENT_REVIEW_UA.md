# A05 · незалежний огляд реалізації

11.09.2026. Оглянуто спільні фінансові команди, архівування, адаптери API/admin,
legacy AI й службові команди лише в межах заморожених місць запису.
Checkout не редагувався; реальні db.sqlite3/BoS_Demo.sqlite3 не читалися.

Основний набір: 32 тести; у журналі root `after-1.log` усі пройшли, разом із
6 A02 та 6 наявними Employee-тестами — 44. Це не повне приймання A05/продукту.

## Знайдені конкретні проблеми

1. **Stale Employee save тихо скасовує архівування.** Прочитаний до archive
   об’єкт Employee потім зберігається старими EmployeeSerializer.update або
   EmployeeAdmin.save_model з усіма полями. Значення archived_at=NULL
   перезаписує справжній архівний timestamp. Детерміновано відтворено два
   допустимі розклади read → archive → save без mocks: Ran 2, failures 2.
   Файли: `a05_archive_stale_regressions.py`, `a05_archive_stale_red.log`.
   Потрібен захист поля archived_at від звичайних save або спільний Employee
   save command. Архів/відновлення повинні бути явними командами.

2. **SET_NULL довідників обходить захист атрибуції витрати.** Реальні API
   DELETE Counterparty/Contract, admin Branch delete та AI delete Counterparty
   обнуляють FK уже проведеної узгодженої зарплатної витрати. Ran 4, failures 4.
   Файли: `a05_attribution_regressions.py`, `a05_attribution_red.log`.
   Прямий Branch DELETE API відсутній; перевірено його фактичний admin writer.
   Вузьке виправлення: PROTECT для Transaction.counterparty/contract/branch
   і зрозуміла відмова API/admin. Root уже додав цей захист, green повтор очікується.

3. **Архівування з помилкою audit INSERT повертає 500.** Сам archive_records
   має atomic і зберігає rollback; спочатку adapters API/admin delete не мали
   узгодженої помилки. Підготовлено три справжні DB-trigger HTTP-тести для API,
   admin single і bulk, плюс audit replay та shared-save rollback.
   Файл: `a05_archive_regressions.py`; red/green цього набору запускає root.
   У поточному code review уже присутні catch і відповіді409.

4. **Archive Employee ↔ create Salary не мали спільного lock.** Початковий
   save_salary(create) читав active status без блокування Employee; для
   PostgreSQL це допускає перевірку старого active до іншого commit archive.
   Це статично встановлений ризик політики, не доведена грошова розбіжність.
   CaptureQueriesContext-тест у `a05_archive_regressions.py` перевіряє реальний
   UPDATE Employee до першого SELECT Employee. Root додав цей UPDATE.
   Фактична конкурентність PostgreSQL лишається неперевіреною без середовища.

## Що огляд підтверджує

Salary/Transaction команди перечитують поточний запис після no-op UPDATE,
платіж A02 бере той самий Salary lock, archive Salary/Transaction — відповідний
row lock. Основні paid CRUD/admin обходи закриті спільною валідацією.
Архів не фільтрується з default manager/фінансових підсумків, джерела та pk
зберігаються; audit записується в тому самому atomic, archive replay не повинен
створювати нового audit або змінювати timestamp. Ці властивості мають лишитися
в regression assertions після виправлень вище.

У цьому огляді не змінювали кількість канонічних дефектів інвентарю,
не проводили аудит ролей A03/A04 і не заявляли PostgreSQL/Windows приймання.
Консенсус для A05 можливий після green додаткових регресій і відсутності
регресій старого набору; продукт визначає лише повний verify.

## Остаточний повторний огляд

Після виправлень root повторно прочитано саме прийняті місця та адаптери.
**Блокувальних зауважень у цій частині A05 більше немає.**

- ArchiveModel.save виключає archived_at зі звичайного update, забороняє
  явний update_fields для нього, не переписує created_at та перечитує поточний
  marker. Stale serializer/admin вже не можуть тихо відновити працівника.
- Archive/restore, фінансова зміна й audit лишаються в спільних atomic;
  API/admin single/bulk перетворюють конфлікт на409 після rollback.
- Transaction FK counterparty/contract/branch мають PROTECT; API довідників
  повертає409, native admin показує залежності, AI відхиляє видалення.
- Створення/перепризначення Salary бере Employee write lock до перевірок;
  Salary/Transaction API та admin, а також legacy AI create використовують
  спільні команди. Валідатор і стан повторно читаються під row lock.
- Міграції0004/0005 додають поля/змінюють on_delete; немає RunPython/SQL
  виправлення, видалення або переписування історичних даних.

Прочитані фактичні журнали root: `evidence/A05/review-after.log` — 6/6;
`evidence/A05/after.log` — 54/54 (включає основний набір, FK, A02 та Employee);
`evidence/A05/stale-after.log` — 2/2. Це огляд коду та підтвердження журналів,
не окремий повтор цих green запусків агентом. Повний verify на момент огляду
тривав; PostgreSQL, Windows і всі інші шлюзи цим висновком не приймаються.

SHA256 оглянутої фінальної `boss_project/archive.py`:
`5acb68a2eaca98e11e4d361bb321a92278f9ffd232e8d51313470d51301a2def`.
SHA256 `finance/commands.py`:
`3ce532e79bcec94b95b9c53ad5d6df62247901e91ee332607e712a6d08babf5d`.
