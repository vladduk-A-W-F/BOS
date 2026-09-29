# Исходник установщика control-home: неактивный архив

Карточка B30-D-CONTROL-HOME-OPERATION-SOURCE завершена как исходник по прямому поручению владельца от 29.09.2026. Независимый verdict: SOURCE_COMPLETE_STATIC_NOT_TESTED_NOT_INSTALLED, SOURCE_FINAL_DELTA_REVIEW_RU.md SHA-256 b42bd8e68d0ce31f0abe73a3774092c2bcba285b5344f96b472640dbbeb20256.

Реализованы пять отдельных фаз snapshot, prepare, alias, activate, verify. Они сохраняют opaque bytes, проверяют полный состав и security metadata, связывают authority и lock identities, требуют точные phase admissions и свежие quiescence receipts, сохраняют partial/failure результаты без автоматического повтора. Это описание принятого исходника, не подтверждение поведения Windows.

## Точный результат

- install_control_home.py: c204737e572de6dadf061bbf3d8a29f6a99938b13f78a03f93664d53ae180a9f
- native_windows.py: 743836205bb0f00e592f6c2a6c26a8c242370213cfb16ec3bdd8581fe8d71add
- OPERATION_CONTRACT.json: 5fc980c404f9ab50633710e950a79168d6db59774a0897cde14e0b3789966d4c
- MANIFEST.json: b1a4bbdfc4e1fd30424d03df9ca77fe902797440ad3ae9a2e63f3090117fd4a8

NATIVE-FLUSH-1 и OPS-1..5 закрыты статическим review. SOURCE_REVIEW_RU.md, SOURCE_REPAIR_REVIEW_RU.md и review-round1/2 сохраняют замечания, воспроизведение по исходникам и точные отклонённые байты. Их CHANGES_REQUIRED не является текущим verdict. Авторские MANIFEST/REPORT оставлены побайтно: pending/SOURCE_COMPLETE=false в них отражает момент до независимого финального review, а не отменяет его.

Принятые зависимости остаются в соседнем control-home-authority-20260928; исходные dependency manifests и review 21c32c1a7835002c55e2d14eec9bea269d29c36a02ed73a53f9b4d497868ac67 не заменены. Архив не является самостоятельным комплектом с разрешением запуска: contract ссылается на точный подготовленный D workspace и будущие отдельно проверяемые входы.

## Что не выполнено

SOURCE_COMPLETE=true только для приведённых байтов и статической приёмки. TESTED=false, INSTALLED=false, MIGRATED=false. Imports, AST/code parser, compile, help, тесты, native probes и installer execution: NOT_RUN; executions=0. Установки, копирования рабочего состояния, смены ACL, config, alias, anchor и действий с приложением в этой карточке не было.

Исторический focused QA остался FAIL_SETUP, попытка 1/1 потрачена, test bodies=0, остальные 21 метод NOT_RUN. C64 и все другие ограничения неизменны. Перед реальным переносом нужны отдельные точные допустимые QA/admissions, свежая общая quiescence и snapshot, независимые phase/commit gates и фактические receipts. Нельзя считать старую остановку writers текущим доказательством тишины.

Root является единственным интегратором. Автор bos3_operation_resume, независимый критический reviewer bos3_d_migration_review; requested Sol/medium и Astra/high, observed UNCONFIRMED. Package review отдельно от code review; его запись добавляется как ARCHIVE_REVIEW_RU.md. Integrated SHA фиксируется после commit в D POST_CHECKPOINT_OPERATIONAL_DELTA.json и root publication receipt; он не выдумывается внутри собственного commit.

Продукт dev9 и последняя runtime-квитанция не менялись; текущая доступность приложения UNCONFIRMED. TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false. Недельный scope и cutoff 04.10.2026 23:59 Europe/Berlin сохранены.
