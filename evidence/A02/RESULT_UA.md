# A02 · одна виплата — одна витрата

Дата: 11.09.2026. До: 6 нових тестів, 4 падіння та 3 помилки у валютних підвипадках. Реальні одночасні HTTP-запити дали різні transaction IDs; повтор повертав 400; EUR/USD записувалися як UAH; два застарілі ORM-об’єкти також відтворили конфлікт блокування. Доказ: `before.log`.

Правка: першою SQL-дією atomic стає UPDATE status=status, що захищає рядок на PostgreSQL і запис на SQLite. Потім перечитується саме поточний Salary, перевіряються стан/наявна витрата та створюється один пов’язаний запис із явною валютою. Повтор узгодженої виплати повертає її попередній результат. Неузгоджена історія потребує звірки; автоматичного переписування немає.

Команда до/після: `BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/a02.sqlite3 BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/a02-media /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B manage.py test finance.test_payment_integrity --settings=verification_settings --verbosity=2 --noinput`. До → 1, після → 0, 6/6 пройшли. Реальний DB trigger відхиляє фінальний UPDATE після INSERT витрати: витрат 0, нарахування pending, повтор після усунення помилки створює рівно 1. Моків бізнес-операцій немає.

Повний verify: `BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite full --output evidence/A02/verify/report.json` → 1. SQLite: 151+5 та 32 Django-тести пройшли; вихідні бази незмінні. PostgreSQL/Windows/CI НЕ ЗАПУЩЕНО, критерії 3–10 ще не реалізовані.

Старий test_pay_again_rejected не змінений: він створює paid без transaction, тобто неузгоджену історію, а не легітимний повтор. Такі дані й надалі отримують 400. Файлова SQLite у тестовому bootstrap потрібна, бо shared in-memory SQLite має іншу поведінку конкурентних блокувань. Це не зміна продуктового профілю і не послаблення перевірки.

Межа доказу: локальна SQLite; PostgreSQL та всі інші обхідні CRUD/admin шляхи A05 ще потребують приймання. Версія 0.2.2-dev.
