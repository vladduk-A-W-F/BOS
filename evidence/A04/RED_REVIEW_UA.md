# A04 · незалежний огляд червоного прогону

Джерело: `/workspace/sites/bos-original-refined/evidence/A04/before.log`.
Зафіксовано координатором після A03 `073ec74`: 43 tests, 153 failures, 5 errors.

## Класифікація

Помилок створення fixtures, неправильних URL, невалідних payload-ів, входу, налаштування БД чи serializer форматів у цьому прогоні не виявлено. Позитивний CEO фінансовий контроль пройшов із трьома валютами. Анонімний клієнт також пройшов усі перевірені GET межі без входу.

Усі п’ять errors мають одну погоджену причину: три старі `_build_*_context` функції ще не приймають `request`. Потрібна зміна продукту за погодженим контрактом. TypeError не слід перетворювати на успішне рішення доступу чи замінювати підміною request/ORM.

153 failures — порушення полів, object scope, додаткових permissions, proposal capability checks та історії чатів. Це кількість невдалих assertions/subtests, а не кількість незалежних дефектів. Зокрема, один не захищений serializer повторно проявляється в канонічному URL та двох format aliases. Два failures видалення історії показують втрату PK замість погодженого архівування.

Відсутність `access_level` є окремим очікуваним schema failure. Helper до міграції дозволив отримати реальні HTTP витоки, тому весь набір не обірвався в setUp. Після міграції він заповнює справжнє поле; поведінка HTTP не підміняється.

Незмінні assertions не потребують виправлень. JSON із групуванням кожного failure/error: `/workspace/scratch/c7b51e996a9f/tmp/a04_red_classification.json`.

## П’ять додаткових категорій обходу

Файл `/workspace/scratch/c7b51e996a9f/tmp/a04_test_blind_paths.py` містить рівно п’ять методів та імпортує прийнятий `operations.test_access.A04SyntheticCase`.

| Категорія | Реальна перевірка | Очікування |
|---|---|---|
| Вкладені referenced IDs | `erp_order.lines[].item_id`, `erp_item.bom[].item_id`, `erp_receive.documents` через обидва preview adapters | Закриті IDs → 404, немає proposal чи бізнес-запису. |
| Сліпі FK у проєкціях | Manager Transaction з прихованим Contract; видимий Item із прихованим BOM item; видима Lot з прихованим document ID | Прибрати закритий FK або весь залежний рядок з відповіді, не змінюючи оригінальні ORM зв’язки. |
| Форми з прихованими джерелами | Requests/quotes create, document review із закритим contract, upload нової версії закритого code | 404 і нуль змін. |
| Відкликані права після виконання | Повтор успішного create_task proposal після відкликання Д | Повторна policy перед поверненням старого receipt; відмова без нового запису чи зміни історичного receipt. |
| Інші renderer/metadata | Browsable HTML та OPTIONS працівників, договорів, transactions | Без закритих значень і назв у JSON, HTML та FK choices. Відсутність HTML renderer з 406 прийнятна. |

Ці категорії прямо входять у прийняту A04 матрицю: referenced records, поля, FK choices, upload закритої версії та перевірка поточних прав на confirm. Немає нових ролей чи модулів.

## Додаткове відтворення

На окремій synthetic SQLite виконано 5 tests: 12 failures, 0 errors. Лог `/workspace/scratch/c7b51e996a9f/tmp/a04_blind_before.log`.

Цей додатковий прогін відбувся на поточному робочому checkout паралельно з реалізацією координатора; це не заява про незмінний знімок commit `073ec74`. Точний початковий red 43 tests зберігається окремо в `evidence/A04/before.log`.

Відтворено дозволені 201/200 для чотирьох сліпих форм; 200 для всіх шести вкладених ERP preview; старий `succeeded` після revoke Д; збережений прихований `bom[].item_id` у проєкції. HTML/OPTIONS перевірка вже пройшла; тест дозволяє безпечний 406.

Оригінальні бази не відкривалися. Зміни checkout не вносилися. Головний файл із 43 тестами та його assertions залишилися незмінними.
