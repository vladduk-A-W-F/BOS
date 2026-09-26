# A04 · початок

11.09.2026. Базовий commit 073ec74cbdc7c369f37456228352655773829573. Прочитано PROGRESS_UA.md після локального завершення A03. Прийнята матриця доступу з планового пакета конкретизована нижче; 43 регресії незалежного автора запускаються до зміни політики продукту. Повний gate4 додатково охопить resolver та всі API/admin methods.

Дані виключно синтетичні; реальні бази не відкриваються й не мігруються. MD5 password hasher у цьому тестовому класі скорочує час численних явних входів; це справжній Django authenticate та HTTP CSRF, без підміни ORM або request.user. A03 окремо перевірено з поточним стандартним password hasher. Робочий профіль хешування не змінюється.

Початковий red: 43 тести, 153 невдалі підвипадки та 5 errors. Усі errors — відсутня погоджена сигнатура context(request), а не збій fixture. Незалежний автор повторно перевірив лог і не знайшов помилок fixture. CEO позитивний фінансовий контроль та анонімні GET пройшли.

Додаткові джерела red: remaining-before-root.log — 3 methods / 10 failures (next-step, replay output, doc FK). boundaries-before.log — 5 methods / 21 failures (admin roles, immutable logs, access revision, HR ordering, DEBUG media). review-response-before-independent.log — 4 methods / 1 failure (однаковий doc FK через відповідь review). Після точкових правок: after-context.log 51/51; boundaries-after.log 6/6. Незалежні логи створювались на рухомому checkout; root редагує один checkout, агенти тільки tmp. gate-before виконується на окремому незмінному знімку до admin fix.
