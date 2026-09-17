# A01 · випуск за повторними резервами

Дата: 11.09.2026. До виправлення: 6 нових HTTP/ORM тестів, 5 падінь. Два резерви 5+5 з партії 10 давали залишок 5 при сумі рухів 0; частковий випуск 6 давав 9 замість 4. Обидва входи preview читали ERP-стан до mutex. Доказ: `before.log`.

Мінімальна правка: один актуальний Lot на ID у межах finish; mutex виділено в helper і взято до fingerprint/«Було» у ERP preview, загальному preview та execute. Після mutex execute перечитує proposal, тому повтор повертає збережений receipt. Порядок резервів, частковий випуск, Decimal і rollback збережено.

Команда до/після: `BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/a01-media /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B manage.py test erp --settings=verification_settings --verbosity=2 --noinput`. До → 1, після → 0; усі 6 пройшли (`after.log`). Перевірки виконують справжні HTTP, CSRF, ORM та SQL; підміни бізнес-операцій немає.

Повний verify: `BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite full --output evidence/A01/verify/report.json` → 1. На SQLite 151+5 і 26 Django-тестів пройшли, регресій у реалізованому наборі немає. Червоними лишаються відсутні критерії 3–10 і середовища PostgreSQL/Windows/CI. Деталі, команди й вивід — `verify/report.json`, `verify/*.log`, `verify-console.log`.

Межа приймання: A01 доведено локально на SQLite, PostgreSQL ще НЕ ЗАПУЩЕНО. Це не повний доказ багатокористувацької роботи або закриття A05/A06. Старі тести не змінювалися. Версія 0.2.1-dev відображається у HTML title та API; візуальна браузерна перевірка НЕ ЗАПУЩЕНА.
