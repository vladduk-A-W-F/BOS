# 0.5 · read-only звірка

Дата: 11.09.2026. До: шість синтетичних регресій не запускаються через відсутній scripts.reconcile_data (before.log). Після: 6/6 пройшли (after.log): відсутні ERP-таблиці не стають green; Decimal 0.1+0.2=0.3; валютна розбіжність вимагає рішення; однакові суми/дати лишаються кандидатами; різниця складської вартості вимагає рішення; source/snapshot SHA не змінюються.

Команда до/після: `BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/reconcile-tests.sqlite3 BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/reconcile-media /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B manage.py test operations.test_reconciliation --settings=verification_settings --verbosity=2 --noinput`. До → 1, після → 0.

Метод: read-only SQLite source → SQLite backup API → read-only query_only snapshot. Явні колонки й Decimal; без ПІБ/контактів/описів, міграцій чи виправлень. Реальний прогін виконано локально; джерело й копія незмінні. Конкретні висновки та SHA — в окремому приватному звіті власника, а не в CI.

Відсутні джерельні таблиці не створювалися заради звірки. Кандидати на дубль не оголошуються підтвердженими дублями або банківськими переплатами. Автоматичного коригування історії немає. Неповна звірка лишається неповною.

Повний verify цього кроку збережено в verify/report.json та логах поруч. Продукт не прийнятий; A03/A04 й зовнішні середовища лишаються обов’язковими.

Остаточний full verify → 1: на SQLite 151+5 та 38 Django-тестів пройшли, чотири інваріанти по 1000 послідовностей пройшли; інваріант доступу має 1000 невдалих послідовностей до A03/A04. Нових регресій немає. Команда full: `BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite full --output evidence/0.5/verify/report.json`.
