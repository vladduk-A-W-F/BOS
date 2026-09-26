# A07 · незалежний огляд мінімальних writer-виправлень

Дата: 11.09.2026. Оновлено після остаточної правки `copy_abs()` та фактичного green додаткових регресій. Read-only огляд checkout `/workspace/sites/bos-original-refined`; зміни й додаткові докази цього агента тільки в `tmp`. Реальні БД не читались. Прочитано фактичні `evidence/A07/boundaries-after-1.log` — **Ran 28 tests in 13.039s, OK** — і `evidence/A07/extreme-after.log` — **Ran 2 tests in 0.855s, OK**. Незалежний повтор цих green-прогонів не виконувався.

## Висновок

**Досягнуто scoped консенсусу writer-частини A07; невиправлених blockers у перевіреному обсязі немає.** Початкові причини 15 writer-регресій усунені мінімальними перевірками на чинних маршрутах. Додатковий залишок N01 з `decimal.Overflow` усунуто безконтекстним `copy_abs()` перед перевіркою місткості; фактичні два тести зелені. Позитивні межі, історичні IDs, три валюти, довільні BinaryField bytes та ідемпотентний повтор не послаблені. Це погодження writers, а не приймання всього A07: перенос, sequence і повний інтегрований verify не зараховані.

## Що перевірено по коду

| Шлях | Причина та висновок |
|---|---|
| `boss_project/data_rules.py:text_value`, `portable_tree` | Перевіряється буквальна довжина Python Unicode string, NUL і непарні surrogate. Вкладені JSON значення й ключі перевіряються рекурсивно. Значення повертається без trim, truncation, заміни Unicode чи перезапису структури. Emoji поза BMP не помилково відхиляються. |
| `erp/service.py:clean` | `portable_tree(payload)` викликається перед ERP mutex і business SQL. Target `field_values` застосовує реальні `max_length`: Invoice.code 30, Item/Lot.revision 40, Location.name/Item.material 200. Старий `.strip()` використано лише для перевірки непорожності коду; новий validator вимірює і зберігає оригінальний рядок. Код із 30 символів і пробілом тепер має 31 й відхиляється. |
| `erp/service.py:dispatch`, `erp/views.py:preview`, `operations/service.py:execute` | Прямий dispatch, preview та повторна валідація pending proposal ведуть до того самого `clean`. Немає окремого permissive writer для confirm. Атомарність, mutex, claim, receipt і replay не перебудовані. |
| `erp/service.py:money_total` та invoice branch | Для Invoice передається `amount.max_digits=14`. Межа перевіряється перед округленням, потім `total=value.quantize(.01)` перевіряється повторно через `decimal_value(total, digits=14, places=2)`. Отже значення на кшталт 999999999999.995, яке округлилося б до 10^12, не може пройти тільки попередню перевірку. Це статичний висновок з порядку викликів; окремий новий тест округлення не запускався. |
| `erp/service.py:invoice` | Перед обчисленням total ще оновлюються `line.invoiced`, але під `@transaction.atomic`; domain ValueError відкочує їх. After-log підтверджує нульову фізичну зміну для dispatch/preview/confirm при 10^12. Спостережений UPDATE перед відмовою не видається за частково збережений рахунок. |
| `erp/service.py:newlot`, `move` | Нові партії перевіряють code/revision/quantity/unit_cost/documents перед INSERT. Новий залишок перевіряється до запису Lot. Чинні знакові Movement, нульовий вивільнений Reservation і допустимий нульовий unit_cost не перетворені на заборонені значення. |
| `operations/views.py:body` та `strict_json_loads` | Повторні JSON ключі, NaN/Infinity tokens і нескінченний decoded float відхиляються. Перевірка відбувається до створення proposal. Вкладений валідний JSON зберігає порядок масивів, bool/null/рядкові суми. |
| `finance/commands.py:_save` | Цільові field checks над `wanted` стоять до `_intent_spec` та атомарного створення intent/source. ValueError перетворюється у ValidationError. NUL/surrogate більше не доходить до запису Transaction/AuditEvent/FinancialIntent. Чинні `candidate.full_clean`, protected paid transition, рядкові locks та A06 intent replay не видалено. Глобального `Salary.save/full_clean` не додано. |
| BinaryField | `field_values` не декодує й не змінює BinaryField. HTTP JSON validator не застосовується до bytes вмісту Document. Позитивний фактичний тест доводить збереження byte sequence із NUL/0xFF/невалідними UTF-8 байтами та SHA. |

## B1 · великий finite Decimal: початковий red, тепер виправлено

Локалізація до остаточної правки; цей опис збережено як історію виявлення:

- `boss_project/data_rules.py:decimal_value`: `abs(amount)` перед перевіркою верхньої межі використовує активний Decimal context.
- `erp/service.py:number`: той самий `abs(n)` для quantity, unit_cost та payment amount.
- `finance/commands.py:_save`: до ValidationError адаптується ValueError, але `decimal.Overflow` не є ValueError.
- `operations/views.py:errors`: Overflow не входить до domain-refusal adapter, тому HTTP повертає 500.

Репродукція використовує **рядки** `"1e9999999"` та `"-1e9999999"`. Вони коротші за поточну межу тіла запиту й є коректними JSON string; `Decimal(...).is_finite()` повертає true. Це не невалідний JSON token і не довільна зміна Decimal context у тесті.

Два нові методи збережено окремо від незмінених первинних 15:

- `tmp/a07_extreme_decimal_tests.py`;
- `tmp/a07_extreme_first.log` — **Ran 2 tests in 0.855s; failures=24; errors=0; exit 1**.

| Writer | Реальний результат |
|---|---|
| ERP opening quantity/unit_cost; payment amount, direct dispatch | 6 випадків: Overflow замість ValueError/ValidationError. |
| Ті самі дані через HTTP preview і підтвердження синтетичного pending proposal | 12 відповідей 500 замість 422. Справжній login і CSRF; без mocks. |
| `save_transaction`, EUR/USD/UAH | 6 випадків Overflow замість ValidationError. |

В усіх 24 викликах повний фізичний snapshot джерел, audit, receipt та intent залишився незмінним. **Це дефект явної відмови для недопустимого розміру, не підтверджена втрата або повтор грошей.** Помилок fixtures не виявлено. Новий прогін дозволено конкретним невкритим ризиком; primary after 28 не дублювався.

### Остаточна перевірка виправлення

Прочитано поточні джерела. `decimal_value` порівнює `amount.copy_abs()` із місткістю поля до `quantize`. У `service.number` використано `n.copy_abs()`, у `money_total` — `value.copy_abs()`, у перевірці коригування залишку — `delta.copy_abs()`. Завдяки цьому великий finite exponent відхиляється явним ValueError, не викликаючи contextual Overflow. Shared finance adapter перетворює його на чинний ValidationError.

Перевірка total після округлення залишилась на місці; allowed magnitude/scale не збільшено. `copy_abs()` повертає копію лише для порівняння, не перезаписує знак, початковий payload, суму або історичний receipt. Збережений `abs(delta)` при обчисленні вартості Movement застосовується після прийнятих обмежень вхідних команд; він не є пропущеною перевіркою місткості в розглянутому caller chain.

`evidence/A07/extreme-after.log` підтверджує: усі 12 HTTP preview/confirm повертають 422, direct dispatch — ValueError, усі 6 shared financial випадків EUR/USD/UAH — ValidationError. Snapshot джерел/receipt/intent незмінний, business SQL writes у ERP-пробах відсутні. **Ran 2 tests in 0.855s, OK**, exit 0 за повідомленням root та успішним логом.

Root переніс додатковий draft у `erp/test_extreme_decimals.py`, замінивши тільки import helper на `erp.test_value_boundaries`; незалежне порівняння тексту підтвердило, що інших змін немає. Старі 15 test methods не успадковуються й не дублюються. Після цієї перевірки B1 закрито; інших конкретних blockers writer-частини не виявлено.

## Обмеження цього погодження

Перевірені CHECK виражають поточні дозволені row boundaries: EUR/USD/UAH, додатні Transaction/Salary, нульовий Invoice, `0 ≤ paid ≤ amount`, `0 ≤ invoiced ≤ shipped`, додатні purchase/production quantity й допустимі accumulated amounts. Вони не ремонтують історичні рядки. Цей огляд не прирівнює їх наявність до завершеного preflight.

Sequence-preserving migration helper та його інтеграція належать окремій задачі; міграції **не прийняті** цим оглядом і не отримали хибного позитивного статусу. Legacy conflict refusal, counts/sums/PK/FK/Binary SHA, sequence preservation, transfer і rollback залишаються за окремими A07 тестами й подальшим повним verify. PostgreSQL **НЕ ЗАПУЩЕНО**. Жодного нового загального дизайну, інвентаризації чи UI scope не додано.
