# A07 · передача синтетичного еталона

Готовий модуль: `tmp/a07_transfer_fixture.py`.

- `populate()` працює лише на вже налаштованій новій verification DB після `migrate`. Відмовляє, якщо domain/auth/session tables або MEDIA не порожні. Повертає JSON-safe manifest з IDs, payloads повторів, фіксованими synthetic timestamps, bytes/base64/SHA та точними row snapshots.
- `verify_facts(expected)` тільки читає configured DB і test MEDIA. Перевіряє незалежні предметні суми, кожну партію/рух/джерело, архівні маркери, JSON, Document/ChatFile bytes, completed/pending proposal і pending fingerprint. Порівнює 42 ORM-моделі. Exact ContentType/Permission/django_migrations rows окремо перевіряє загальний transport manifest за рішенням root; remap цих IDs не заявлено.
- `verify_replays(expected)` виконує справжні команди **лише на похідній disposable proof-копії DB і MEDIA**, з `BOS_A07_PROOF_COPY=1`. Відмовляє на source DB/MEDIA з `expected.origin`. Використовує перенесений session cookie та справжній CSRF endpoint, не login bypass. Після одного completed HTTP replay виконує 3 archived Salary.mark_paid і 6 keyed financial retries. Вимагає ті самі IDs та точні rows; єдина дозволена зміна — `Configuration.erp_write.value.revision + 1`. Джерело та прийнятий target ізолює caller; source додатково захищений explicit origin check.

Для кожної EUR/USD/UAH: raw **13.000**, finished/returned **2.000**, stock value **39.00**, production actual **12.00**, Invoice **15.00**, paid **5.00**, open **10.00**, finance in **200.00**, out **100.00**, net **100.00**. Валюти не додаються між собою.

Матеріальні counts: 12 Lots, 18 Movements, 9 Reservations, 66 ERP Events, 3 Invoice/InvoiceLink, 3 paid archived Salary, 3 archived salary expenses + 3 manual incomes, 6 FinancialIntent, 2 proposals, 3 Documents з IDs **7/1001/90001**, 1 archived ChatMessage + реальний ChatFile. Версії A/B обох документів збережені; активний допуск приймає лише latest B. Text-only Document із порожнім BinaryField також збережено буквально.

Усі грошові й складські факти виконано чинними ERP/shared/mark_paid командами. Документи схвалено через HTTP; archived chat — через HTTP. Після команд змінено тільки timestamps нової synthetic fixture та відповідні archive audit timestamps для фіксованого еталона; гроші, кількості, статуси й джерельні IDs не переписувались.

## Фактична перевірка

Перший setup зупинився через **помилку fixture-oracle**: він очікував незмінність службового ERP mutex під час completed replay. A06 навмисно інкрементує mutex на 1. Збережений `tmp/a07_fixture_first.log`; виправлено тільки це очікування. Business/receipt assertions не послаблено, у фінальному transfer snapshot кінцева Configuration порівнюється точно.

Другий прогін на іншій новій SQLite: `populate → JSON serialize/parse → verify_facts`, відмова повторного populate на nonempty та повторна незмінність фактів — **exit 0**. Лог `tmp/a07_fixture_second.log`; початковий manifest `tmp/a07_fixture_expected.json`.

Після додавання окремого replay helper створена похідна копія цього синтетичного source, окрема MEDIA та доповнений лише metadata/payloads manifest `tmp/a07_fixture_replay_expected.json`. Прогін **exit 0**: `tmp/a07_fixture_replay_proof.log`, результат `tmp/a07_fixture_replay_result.json`. HTTP повернув тотожний receipt; Salary/FinancialIntent retries повернули старі джерела, фінанси й склад незмінні. SHA початкового source DB і кожного source media file до/після однакові.

Це **перевірка source fixture та replay на її похідній proof-копії**, не вже виконане SQLite→PostgreSQL перенесення. Root запускає перший повний transport trial з цим модулем. PostgreSQL тут **НЕ ЗАПУЩЕНО**. Модуль не мігрує БД, не імпортує дані й не змінює sequences; ці докази залишаються за окремим driver.

Приклад контракту driver:

```python
# source worker: fresh DB migrated by caller
expected = populate()
# after import: independently configured target worker
verify_facts(expected)
# derived proof worker, with copied DB/MEDIA + BOS_A07_PROOF_COPY=1
replay_report = verify_replays(expected)
# only then the driver's two ordinary Document inserts for sequence proof
```
