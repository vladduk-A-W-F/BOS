# A03 · відтворення

11.09.2026. Робоча тека: `/workspace/sites/bos-original-refined`.
Для всіх Python-команд: `BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages`.
Python: `/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python`.

| Команда / контекст | Вивід | Результат |
|---|---|---|
| `manage.py test employees.test_identity --settings=verification_settings --noinput -v 2` на свіжій синтетичній SQLite | before.log | 29 тестів; 23 падіння й 9 помилок підвипадків до реалізації |
| Та сама команда після входу й прив’язки User | after-1.log | 29/29 |
| `manage.py test employees.test_identity_stale --settings=verification_settings --noinput -v 2` | stale-before.log | 2 падіння; стара форма стирає user_id |
| Додано `finance.test_archive_stale` до попередньої команди | stale-after.log | 4/4 після захисту command_fields |
| `manage.py test employees.test_login_concurrency --settings=verification_settings --noinput -v 2` | rate-before.log | Один провал: після 8 завершених невдалих HTTP-входів наступний також 401 |
| `manage.py test employees.test_login_ticket --settings=verification_settings --noinput -v 2` | ticket-before.log | Один провал: запізнілий успіх стирає новішу невдалу спробу |
| `manage.py test employees.test_identity employees.test_identity_stale employees.test_login_concurrency employees.test_login_ticket finance.test_archive_stale --settings=verification_settings --noinput -v 2` | after-3.log | 35/35; з них 33 нові A03, 2 попередні архівні |
| `manage.py makemigrations --check --dry-run --settings=verification_settings` | migrations-check.log | No changes detected |
| `node scripts/build_frontend.cjs` | frontend-build.log | Побудовано assets/app.js; браузер не запускали |
| `bash scripts/verify.sh --suite full --output evidence/A03/verify/report.json` | verify/ | Перший проміжний: SQLite 151+5+111 |
| `bash scripts/verify.sh --suite full --output evidence/A03/verify-final/report.json` | verify-final/ | Другий проміжний до UUID ticket: SQLite 151+5+114 |
| `bash scripts/verify.sh --suite full --output evidence/A03/verify-reviewed/report.json` | verify-reviewed/ | Остаточний код після незалежного огляду; факти тільки у report.json |

Кожен прямий Django-прогін мав власні `BOS_TEST_DB_NAME=/tmp/bos-a03-*.sqlite3` та `BOS_TEST_MEDIA=/tmp/bos-a03-*-media`; backend доводить verification_settings. Повний verify створює окрему копію вихідного коду й нові синтетичні бази для кожної підперевірки. Оригінальні БД контролюються SHA до/після, не використовуються як fixtures.

Незалежні команди: `rate_process_probe.py` запускає шість різних Python-процесів і зберігає RATE_PROCESSES_AFTER.json; `compare_assertions.py` виконує AST-порівняння проти базового commit. Це додаткові докази, не заміна 11 критеріїв.
