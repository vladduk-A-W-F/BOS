# A05 · відтворення

Дата: 11.09.2026. Усі standalone Django-команди запускалися з наведеним префіксом; кожна мала окремі `BOS_TEST_DB_NAME` та `BOS_TEST_MEDIA` у /tmp. Реальні бази не використовуються як test NAME.

```bash
BOS_TEST_MEDIA=/tmp/bos-a05-before-media BOS_TEST_DB_NAME=/tmp/bos-a05-before.sqlite3 BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python manage.py test finance.test_finance_integrity --settings=verification_settings --noinput -v 2
```

| Лог | Labels після `test` | Результат |
|---|---|---|
| before.log | finance.test_finance_integrity | exit 1, 32 тести / 52 невдалі підперевірки |
| after-1.log | finance.test_finance_integrity finance.test_payment_integrity employees.tests | exit 0, 44/44 |
| review-before.log → review-after.log | finance.test_archive_regressions | 6 тестів: 4 падіння → 6/6 |
| attribution-before.log | finance.test_attribution_regressions | exit 1, 4/4 падіння |
| after.log | finance.test_finance_integrity finance.test_archive_regressions finance.test_attribution_regressions finance.test_payment_integrity employees.tests | exit 0, 54/54 |
| stale-before.log → stale-after.log | finance.test_archive_stale | 2/2 падіння → 2/2 пройшли |

Для міграцій використовувався той самий профіль verification_settings і нова /tmp/bos-a05-migrations.sqlite3: `manage.py makemigrations finance employees ai_assistant --settings=verification_settings --noinput`, потім окремо `finance` для FK. `makemigrations` лише створює файли; застосування на порожній базі — у verify.

Збірка frontend: `node scripts/build_frontend.cjs` → exit 0, frontend-build.log. Це не браузерне приймання.

```bash
BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite full --output evidence/A05/verify/report.json
```

Повні команди ізольованих subprocess, дати, середовище, digest коду та SHA вихідних баз зберігає verify/report.json. `test` сам видаляє тимчасові БД; робочі бази незмінні. Історичні red журнали збережено.
