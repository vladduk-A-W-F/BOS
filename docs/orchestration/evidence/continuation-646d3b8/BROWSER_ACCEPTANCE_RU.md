# BoS: проверенный браузерный кандидат и локальный просмотр

Root ACCEPT_SCOPED,20.09.2026. Commit646d3b80597e087a1ada14221024ec40588996f0; source98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a.

Настоящая attempt5: exit0, Gate10 семь из семи (200% nativezoom,390/768/1440,клавиатура/Escape,ошибка сети/recovery,UAH preview/confirm). Root сверил все26артефактов по SHA и длине, raw и report hashes. Report SHA be0ab0e51ce4d03093bbbadf4168dbd626298817f426cc485199f56fc46592e4; raw SHA4acaac1736918eebf9b9b6ff8e564f5eae61efc2434c564ef5141fbc4d40f3e8.

Отдельно три новых сценария: перемещение1единицы,оплата12.34UAH,unsupported_document для обычного документа. Первые два прошли UI preview/confirm и HTTP replay того же proposal в той же браузерной сессии; root сверил before=after_preview и after_confirm=after_replay business hashes. Это локальный синтетический учёт, не банковская операция и не полный Gate6. Документ не породил записей или вымышленных полей.

Владение процессами проверено до импорта приложения. Child8084 и launcher12712 подтверждённо завершены, одноразовая среда удалена; исходники и исходные БД неизменны. Attempt4 сохранена FAIL из-за focus restore; отдельный исправляющий commit646d3b8 прошёл независимое source review и затем настоящий browser assertion без ослабления.

Постоянный экземпляр: http://127.0.0.1:8876/ ; D:/3/Codex/2026-09-20/bos-execution/work/continuation-review-demo-20260920. Отдельные учебные SQLite/media. Проверен обычный CEO login, nonstaff/nonsuperuser, working mode,AI не подключён. Root дополнительно прочитал public csrf live200 и просмотрел1440screenshot; пароль не читал. Контроллер оставляет только доказанные принадлежащие стенду процессы. Руководство и show-login.ps1 находятся в continuation-focus-frozen-20260920/local-review-support.

Приём относится именно к646d3b8. Слияние PR2 ещё не выполнено: две ветки содержат пересекающиеся миграции и различные финансовые значения удержаний. Полные PG/E2E, same-N restore, install/upgrade и остальные11gateconditions не считаются закрытыми. TECHNICAL_READY=false,PILOT_ALLOWED=false.
