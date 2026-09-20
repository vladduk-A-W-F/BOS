# VERTICAL-UA-UI · 20.09.2026

ACCEPT_SCOPED: root незалежно переглянув diff автора ua_vertical_ui_audit і перевірив інтегрований JSX на реальних Django JSON трьох ролей. Allowlist: frontend/boss_app_source.html, generated boss_app_html.html/assets/app.js, scripts/build_frontend.cjs (compact:false), scripts/check_workpoints_ui.cjs, ця картка.

Реальний BoSHome містить робочі точки/схему координат, чотири групи процесу, чинні inspector/trace/docs/NextAction/preview/confirm. UAH default нових форм, explicit preset currency збережено. Decimal strings і null не перетворюються на вигадані суми. Workpoints→snapshot→workpoints звіряє публічні дані/access revision; це optimistic consistency, не atomic snapshot. Помилки/відкликання/зміни очищають факти. HTTP telemetry — останні20 запитів сесії до response headers, без URL/ID/body, не business speed.

20 controlled actual-JSX cases +3 captured real Django role contracts PASS; native build/syntax PASS; інтегрований lexicalchecker PASS після окремої FRONTEND-GLOBALS картки. Browser/DOM/viewport/E2E ще не прийняті цим доказом; окрема локальна browser-картка дозволена новим уточненням A11. Readiness/pilot=false.
