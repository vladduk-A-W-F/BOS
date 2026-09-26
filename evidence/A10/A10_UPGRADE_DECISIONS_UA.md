# A10 · незакрита частина: оновлення й rollback

Підготовчий read-only аналіз root, 12.09.2026. Це не виконання й не приймання gate 9. Код поточного full verify не змінюється.

## Контракт, який треба завершити до реалізації

1. Оригінальні код, конфігурація, DB і приватні файли N залишаються на місці. N+1 створюється тільки у власному новому candidate; forward migrations виконуються лише там, під доведеним quiescence N. Копіювати venv зі старими абсолютними shebang не слід: створити нову venv з тих самих перевірених офлайн pins/provision helpers.
2. Candidate використовує installation UUID/secret/origin N, але нові власні code/config/state/runtime paths. Не перенумеровувати User/Employee/фінансові записи.
3. Перевірка N+1 до cutover повинна пропускати лише справжні GET health/version. Звичайний записуючий WSGI не можна тимчасово відкривати як staging: тоді rollback уже може втратити записи. Probe process належить поточному controller; після proof повністю зупиняється.
4. File descriptor/typed sealed capability самі по собі не доводять міграції або фінанси. Потрібна фактична звірка незмінних таблиць/ID/FK/Decimal/послідовностей/медіа з N; дозволені лише точно відомі зміни migration metadata/DDL. Для gate 9 — два реальні пакети, зокрема синтетичний N+1 з реальною additive index migration, а не одна зміна VERSION.
5. Activation тримає спільний lock із release та змінює тільки власний atomic pointer/append-only receipts. Читання torn history/pointer повинно відмовляти без автоматичного repair.
6. Важливий незакритий випадок: старий A09 launcher не читає generations/ACTIVE.json. Після активації N+1 він не повинен запустити N і приймати записи в стару DB. Простого нового wrapper недостатньо: потрібне відключення старої launch-readiness у довіреному registry, яке старий launcher вже перевіряє. Це не бізнес-дані.
7. Нинішній prototype ledger хешує весь original registry record та викликає load_owned, який вимагає application_provisioned=true. Тому відключення старої launch-readiness зламає його anchor. До приймання слід чітко розділити незмінний доказ оригінальних ресурсів та змінну готовність/активне покоління. Не виправляти це примусовим true, зміною чужого receipt або вимкненням ownership-перевірки. Потрібен явний read-only inspector original resources, окремий від дозволу запуску.
8. Новий managed runtime повинен читати видане current-owned покоління; same-N controller зараз правильно відмовляє за ACTIVE. Перевірити одночасний старий/new launcher та відсутність запуску N при активному N+1.
9. Rollback дозволений лише до нових записів у N+1. Консервативно порівнювати native DB SHA та весь private inventory із станом перед відкриттям записів; будь-які зміни, включно з новими сесіями, мають відхилити rollback, доки немає окремої узгодженої стратегії перенесення. Не переписувати/видаляти історію після нових оплат або рухів.
10. Фактичний позитивний gate 9: N → native backup → N+1 forward migration → read-only ready → rollback N → exact code/config/data/media/sequence proof → реальний запуск N. Окремий негативний сценарій: запис у N+1 → rollback refusal → запис лишається. Це синтетичні дані, не клієнтська установка.

Поточний prototype activation не прийнятий. Він не має операторського CLI. Виправлення stdin CLI/backup/clean restore не закриває ці пункти. Нові framework/черги/shared DB або мережеве керування не потрібні.
