# B30-12-QA-SCOPE: независимый review первой подготовки

27.09.2026. Author existing QA thread01a0c05d-6eeb-79f1-a135-be66985b442f; независимый reviewer start_overview_review. Verdict CHANGES_REQUESTED, NOT_AN_EXECUTABLE_QA_PLAN. Исходные три артефакта сохранены неизменными в attempt1/, hashes совпали: MD3a41b3a67a9f75249939fc49f858225dd741f90bc0760200dc724c2f8a862951; JSON01d662dd9db52cba670dd41820c4a8c07b38df1d48cc79f6e89204179a8ba674; author77422d5e1fd1d7172afa9eedfa2e0d3111fde3d9bf842e5d9101549734793b35.

1. P1: S1/S2/S3 описаны как business narratives, без candidate-bound role/UI/API route/command-service symbol/source path, точных переходов/receipt/ожидаемых значений. Это требования к будущему плану, не исполнимый oracle.
2. P1: S2 пока требует mapping decision, но уже включён в общий proposed exception. Сначала завершить read-only mapping либо оставить S2 отдельно с явным blocker; нельзя разрешать неопределённый document-to-draft-to-confirm путь.
3. P1: cap ledger глобальный, не по proposed run. Требуются NEW/SAME-PROBLEM, максимумы и пересечение S1/payment с исчерпанным network/payment. Общий exception не покрывает неопределённость.
4. P2: synthetic environment не привязана к точным root/DB engine/name/media/marker/evidence/retention/emptiness/write allowlist. Подготовить конкретное предложение до запроса.
5. P2: broad historical evidence без точных путей/commit applicability; добавить конкретные requirement rows, oracle и stop condition.

Корректно: execution-disabled scope, caps не сброшены, ложного QA PASS нет. Read-only review не запускал продукт/браузер/runtime/setup/БД. Следующий шаг существующему автору: узкая доработка тех же артефактов. До следующего независимого review не отправлять owner execution question и не выполнять проверки. Root дополнительно требует различать фактические учебные supply/quality/payment и более широкие S1/S2/S3; отсутствие их соответствия не оправдывает новый сценарий или изменение реализации.
