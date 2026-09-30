# ARCH-01: исправление предложения среды до исполнения

27.09.2026. Предложенный root в dcb184a learning SQLite `db.sqlite3` несовместим с exact-f55 training/access.py:21–29. Это ошибка спецификации будущей проверки; среды нет, продукт/guard/runtime не менялись. Исходное предложение сохранено исторически в REVISION3_REVIEW_RU.md. Architect bos_architect обнаружил, tracker проверил, root прочитал exact Git blob, независимый start_overview_review дал минимальный correction-contract.

Текущее единственное предложение: D:/3/BOSDev/qa-runs/b30-12-learning-f55-r1/bos3-fasteners-f55-r1.sqlite3. Engine SQLite only; media/, evidence/, RUN_MANIFEST.json внутри того же будущего root. Ни файл, ни каталоги не созданы. Это не PostgreSQL/11gate evidence.

До разрешённого будущего writer должны совпасть: BOS3_TRAINING_ENABLED=1, BOS_DATA_MODE=demo, BOS3_TRAINING_PROFILE=isolated-synthetic, BOS3_TRAINING_DB_MARKER=bos3-fasteners-uk-v1; sqlite vendor, имя с bos3-fasteners, отсутствие online-review и запрещённых review.sqlite3/db.sqlite3/bos_demo.sqlite3/bos_working.sqlite3. Точная resolved path identity связывается SHA-256, не переносится с owner-local.

Configuration['bos3_fixture'] должен иметь id=bos3-fasteners-uk-v1, synthetic=true, schema=1, source_map как dict с полным набором объектов выбранного fixture, hash exact f55 erp/seed/bos3_fasteners_uk_v1.json, непустые installation_id/owner_username, owner_user_id и database_identity_sha256 от resolved DB path. Guard проверяет тип source_map; полнота карты дополнительно нужна предлагаемому oracle, не выдуманное условие guard. BOS3_TRAINING_INSTALLATION_ID и BOS3_TRAINING_OWNER_USERNAME совпадают с marker. Actor user.pk/username совпадают для enforce_training_identity и require_training.

RUN_MANIFEST.json является QA evidence marker, а не заменой Configuration['bos3_fixture']. Будущий согласованный manifest обязан связать source f55, fixture/hash/schema/map, installation/owner identities, resolved DB hash, media, writer allowlist и raw evidence root. При несовпадении остановиться до writer; setup/fixture также требуют отдельного допуска и не выполняются из этого документа.

Независимый reviewer start_overview_review подтвердил этот минимальный контракт read-only. Root исправляет current CONTROL proposal; действующий QA уже получил ARCH-01 и должен включить контракт в exact learning plan. Пока QA alignment и полный oracle не приняты, общий B30-12-QA-SCOPE PARTIAL/not authorized. Никаких новых execution attempts; первоначальная ошибка не скрыта, caps не обнулены.

ARCH-02 отдельно передан существующему design owner: documentary receivable label, без UI/formula/build/browser изменений. Его correction ещё не принята этим документом. Architecture packet принят как read-only handoff, не как закрытие обоих findings или готовность продукта.
