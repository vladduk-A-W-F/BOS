# B30-PREVIEW-DELIVERY: фактическое независимое ревью

27.09.2026. Reviewer start_overview_review, исполнитель root. Verdict: **ACCEPT_SCOPED_DELIVERY_AND_ENTRY**. Проверены raw capture/stop/apply/start exits, attestation, stopped preflight, maintenance receipt, post-start identity/payload proof, browser-entry.json и сохранённые desktop/mobile screenshots.

Подтверждено ровно одно разрешённое окно: 33d7d387aa582c04339a91ae94361948ea67904c -> immutable f55a15de4006d10c0d7c65f8a2ca8499fbb99819; 12 product paths; capture/stop/apply/start по одному, native exit 0. Новый clean source digest bd7031ef15282924411c2ec386b5f882fda9f7589253cfad5c84a9ee53b8aa3c. Старый PID identity совпадает в capture и verified stop; новый waitress PID 40776 связан с точным source/digest и единственным loopback listener.

Aggregate data/media/credential hash до остановки и после старта совпал: 1e44bae003f9c1290e6ac7d99c9d1f4eb6230c507e032452b65803c6f532d7e4. Это момент до browser login; auth session changes после обычного входа не объявляются byte-identical БД. Init/seed/migrate/reset/rollback не выполнялись.

Scoped browser evidence подтверждает светлое превью до входа, выбор кейсов, desktop 1365x900, mobile emulation 390x844, один обычный вход и сохранение payment в состоянии not_started. На сохранённых снимках reviewer не обнаружил наложений или горизонтального переполнения. Отсутствующий прежний tab и начальная ошибка binding документированы: переиспользован тот же новый tab, не второй acceptance run.

Не проверялись: negative private API/role boundary, физический телефон, выполнение уроков, ERP/CRM mutations, full browser/E2E, fixture/reset, внешний доступ или release gates. Это не полная приёмка. TECHNICAL_READY/PILOT_ALLOWED/MVP=false. Успешное окно не повторять без новой конкретной причины и применимого допуска.
