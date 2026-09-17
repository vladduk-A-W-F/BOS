# 0.6 · PostgreSQL

Дата: 11.09.2026. Статус: НЕ ЗАПУЩЕНО. Приймання на PostgreSQL не відбулося.

Команда: `BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite postgres --output evidence/0.6/verify/report.json` → exit1. Обов’язкові підперевірки не стали зеленими. Локальний PostgreSQL/container runtime відсутній; немає налаштованих BOS_PGHOST/USER/PASSWORD та BOS_PG_DISPOSABLE=1. Події робочихБД не читалися.

Профіль уже підготовлено в0.0: PostgreSQL16 уdocker-compose.yml та GitLabCI, psycopg уrequirements-ci.txt, перевірка фактичного vendor, окремі тимчасові бази зі строго перевіреним власним ім’ям. Немає remote BoS або доступного GitLabconnector; репозиторійFOS — інший проєкт. Публікації чи запуску в чужому проєкті не було.

Потрібні адреса й доступ доCI-репозиторіюBoS або ізольований PostgreSQLruntime. Windowsrunner також лишається незапущеним. Це не підстава зупиняти інші погоджені задачі за§2.1 masterv2.1: наступнаA03, післянеїA04. Код не змінено нацьому кроці, останній повнийverify зтим самим source_digest — evidence/A05/verify/report.json; тутзафіксовано окрему спробу postgres suite.
