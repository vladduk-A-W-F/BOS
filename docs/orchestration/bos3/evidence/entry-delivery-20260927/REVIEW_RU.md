# B30-04D: подготовка контролируемой доставки

Дата 27.09.2026. Автор bos3_fixture_impl; независимый reviewer start_overview_review. Verdict ACCEPT_SCOPED_STATIC, исполнений нет. Root хранит reviewed копию runner рядом с этой записью; файл не является автоматическим разрешением на обслуживание.

Runner SHA-256: 09ed0a9f1b535c6607fe82d3bb71689ec1259ddbc4c527fc206710e03359af57.
Старый runtime: 33d7d387aa582c04339a91ae94361948ea67904c.
Новый неизменяемый product pin: ae966d3e70d951318f7c13dc5488cd9cc6d663c3.

Проверены закрытия P1/P2: новый SHA закреплён константой, проверяется capture и attestation, apply требует совпадения CLI и attestation; единственный listener может быть только 127.0.0.1 или ::1. Точная БД root/data/bos3-fasteners.sqlite3, prepared digest и неизменность data/media/credential bytes проверяются без вывода секретов. Binary PNG проверяется из закреплённого Git blob до переключения source.

Allowlist ровно 10 delivery файлов: assets/app.js; assets/bos3-fasteners-entry.png; boss_project/refinement_views.py; boss_project/version.py; docs/BoS_3_0_Start_UA.manifest.json; docs/BoS_3_0_Start_UA.pdf; frontend/bos3_content.json; frontend/boss_app_html.html; frontend/boss_app_source.html; scripts/build_bos3_brochure.py. Документы оркестрации не являются продуктовой доставкой; README исключены. Позднейший docs HEAD нельзя подставлять вместо immutable product pin.

Runner не импортирует Django, не вызывает init/migrate/seed/start/stop/rollback. Никакие capture/apply, browser, DB или lifecycle-команды не исполнялись. Вопрос об одном controlled update/restart предъявлен владельцу; ответа пока нет. До явного ответа не исполнять ни один режим.

Остаточный операционный риск: сбой записи prepared metadata после source switch способен оставить остановленный checkout на новом SHA. Автоматического rollback намеренно нет; потребуется явное контролируемое восстановление. Изменение защищённых файлов между capture и apply означает fail-closed отказ, а не разрешение повторять обслуживание или возвращать старые пользовательские данные.
