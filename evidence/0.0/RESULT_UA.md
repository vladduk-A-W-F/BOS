# 0.0 · результат

Дата: 11.09.2026. Python 3.12.14, Linux; Django 6.0.5.

До: `bash scripts/verify.sh --suite full` → 127, команди немає (`BEFORE.json`).

Після: `BOS_PYTHON=/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages bash scripts/verify.sh --suite full --output evidence/0.0/after/report.json` → 1. Усі 11 критеріїв присутні. На SQLite міграції, 151 + 5 та 20 Django-тестів пройшли; відсутні реалізації позначено червоними. Повний вивід: `after/console.log`, покрокові результати й середовище: `after/report.json` та логи поруч.

Чотири старі функціональні скрипти отримали лише вибір ізольованої СУБД і доказ фактичного engine; тіла перевірок не змінено (`ORIGINAL_CHECKS.json`). П’ять launcher-перевірок збережено повністю; вони не заміняють Windows. Кожний скрипт отримує нову синтетичну базу. SHA вихідних SQLite незмінні.

Зовнішній CI: НЕ ЗАПУЩЕНО. Git remote відсутній; підключений GitHub показує тільки окремий FOS; пошук GitLab-плагіна не дав підключення. Потрібна адреса й доступ до CI-репозиторію BoS. Посилання на фактичний pipeline відсутнє; приймання 0.0 у GitLab не завершене. PostgreSQL: НЕ ЗАПУЩЕНО (немає runtime/ізольованого сервісу). Windows: НЕ ЗАПУЩЕНО (немає runner). Готові pipeline, compose та інструкція runner знаходяться у коді. Пункт 2.1 master v2.1 дозволяє продовжувати решту локальної роботи за цих обмежень.

Незалежна перевірка виявила неповний SHA набору коду й зайве копіювання .venv-ci. Обидва зауваження виправлено перед остаточним запуском. GitLab YAML розібраний локально; це не GitLab Lint і не запуск pipeline.
