# B30-PREVIEW-PACK: версия и вспомогательная памятка

27.09.2026. Автор: «БОС — реализация и проверка пакетов», 01a0be9f-b413-7822-9f93-16ba69f4f00f. Отдельная копия D:/3/BOSDev/tmp/bos3-preview-pack-20260927 от defd1fc12545053159a3a888013d096c79157fd3. Root интегрирует после независимого review, main/runtime не изменяются.

Allowlist: README.md, README_UA.md, boss_project/version.py, docs/BoS_3_0_Start_UA.pdf и docs/BoS_3_0_Start_UA.manifest.json. Новый reviewed registry механически передан как вход сборщика; сам UI и исходные сценарии упаковщик не менял.

## Проверка

Независимый reviewer bos3_preview_archaeology: ACCEPT_SCOPED_STATIC. Подтверждены состав diff, версия dev.3 в version.py/manifest/PDF и просмотрены все три уже созданные PNG страницы. Текст читаем, наложений/обрезаний не обнаружено. README и PDF отделяют код от runtime, не заявляют browser acceptance или production readiness. Root отдельно прочитал README/version diff; блокирующих замечаний нет.

| Артефакт | SHA-256 |
| --- | --- |
| README.md | 667b30127e2a18d238d92650e3230a212ee93827e9338ade12019565daa497c6 |
| README_UA.md | c9e14ce3e53089cee81c24314d77ef525da7411b14b9d020b191ccdab6fdfe89 |
| boss_project/version.py | c17837bccbc5092a62eed7faaf5cd794a040827e03531b254e22d1406287f286 |
| frontend/bos3_content.json | 1bce859370537437c157893065af499c9edd0fefea90b30c2f3384b2b04b1390 |
| docs/BoS_3_0_Start_UA.pdf | 592977c117527cfd1a36aa5df08f819d1b2e2896e4bb3adf89ab12ff7e7c1610 |
| docs/BoS_3_0_Start_UA.manifest.json | 836365389f3304163d0221d69dcdbbc89b88b5fc3eb01dc607e9cdeb189b987a |

Штатный builder: `scripts/build_bos3_brochure.py --registry frontend/bos3_content.json --output docs/BoS_3_0_Start_UA.pdf --version 0.3.0-dev.3`, native exit 0. Рендер всех трёх страниц через pdftoppm, native exit 0. Manifest/version/PDF/registry consistency PASS. `git diff --check`, exit 0.

Первый dev.3 PDF был создан до дополнительного поручения владельца о charts. После нового registry hash выполнена одна обоснованная регенерация; старые PDF/manifest сохранены отдельно, не выданы за финальные. Источник raw и рендеров: D:/3/BOSDev/tmp/bos3-preview-pack-20260927-evidence/registry-rebuild-20260927/. EVIDENCE_MANIFEST.json SHA-256: 12984a174e1e068fade87023290703626a1b8a0e0fc29fd38cc8d52cf920c4d8.

Environment note: при первом запуске builder в выделенном задании не было reportlab; упаковщик установил его в D:/3/BOSDev/venv, затем сборка завершилась. Изменение среды зафиксировано, не считается product acceptance. Последующая регенерация без установки пакетов. Runtime не перезапускался.

PDF остаётся вспомогательной памяткой. Web preview является основным стартовым экраном. Статическое и визуальное review PDF не доказывает браузер, прохождение уроков, сохранение прогресса или доставку dev.3. TECHNICAL_READY/PILOT_ALLOWED/MVP=false.
