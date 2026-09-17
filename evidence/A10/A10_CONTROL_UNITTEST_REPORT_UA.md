# Постійні перевірки керованого обслуговування BoS

Результат: **10/10 методів unittest успішні, 0 пропусків**, 2,165 с. Запуск через `unittest discover` використовував канонічний checkout; файли продукту не змінювалися.

Для інтеграції:

- `a10_control_unittest_draft/boss_project/test_maintenance_control.py` → `boss_project/test_maintenance_control.py`.
- `a10_control_unittest_draft/fixtures/synthetic/maintenance_wsgi.py` → `fixtures/synthetic/maintenance_wsgi.py`.

Зафіксовані SHA і точний перелік методів: `A10_CONTROL_UNITTEST_FROZEN.json`. Повний результат: `A10_CONTROL_UNITTEST_DISCOVER_FINAL.log`.

Канонічні імпорти: `scripts.install_server`, `scripts.maintenance_control`, `scripts.start_server`. Копій реалізації продукту, alternate-module параметрів, mock Popen, штучних drain receipt та пропусків для відсутнього коду немає. Фактична версія Waitress перевіряється в основному процесі та WSGI subprocess: 3.0.2.

Збережені сценарії:

1. Реальний lifetime flock відмовляє другому supervisor; невидана capability і receipt від стороннього object не приймаються.
2. Активний HTTP-запит утримує справжній SQLite writer. До його завершення lease немає; після звільнення доведені HTTP 200, запис у SQLite, нуль writers/workers та exit 0.
3. Callback читає незмінену базу під живим `fenced_for`.
4. Інші installation ID, root, operation ID і зміна публічних прив’язок lease відхиляються.
5. Наявність ACTIVE відмовляє відновленню N і новому same-N запуску до створення дочірнього процесу.
6. Fence затримує конкурентний release; після виходу запускається новий власний процес, стара lease недійсна.
7. Фактичне зняття kernel flock інвалідовує lease; збіг inode не замінює блокування.
8. Закритий owner інвалідовує lease, окремий власний тестовий canary процес залишається живим.
9. Реальний drain timeout дає exit 6, без lease та quiescent event; звільнення writer після exit не створює відкладеного запису.
10. Повний same-N цикл з двома поколіннями зберігає базу та закриває всі власні процеси.

Кожен метод окремо перевіряє cleanup: жодного живого власного дочірнього процесу, reader або робочого потоку; байти admission SQLite та канонічних config/manifest незмінні. Усі файлові зміни — у нових тимчасових каталогах.

Межа доказу: registry/bundle є явно синтетичною unit-фікстурою admission condition контролера. Це **не доказ provisioning, міграцій BoS, TLS, backup, restore або upgrade**. Ці acceptance gates перевіряються окремим повним стендом. Unix IPC не використовується й не оголошується перевіреним.
