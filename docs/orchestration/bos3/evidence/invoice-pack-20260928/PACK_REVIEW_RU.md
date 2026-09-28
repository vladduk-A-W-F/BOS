# B30-INVOICE-PACK-DEV8: независимый package review

Дата: 2026-09-28

## Проверенный scope

Проверен frozen package из пяти allowlisted файлов относительно exact source `c00c60aad0c4f8e70251da3c7174ed105089198b`:

- `repo/boss_project/version.py`;
- `repo/README.md`;
- `repo/README_UA.md`;
- `AUTHOR_REPORT_RU.md`;
- `MANIFEST.json`.

Никакие application logic, assets, PDF, build, тест, import, runtime, DB или network не запускались и не проверялись этим review.

## Факты

- `c00` является предком текущей D canonical; в последующей документальной дельте три mirror-source файла не менялись. Source SHA-256 из manifest совпадают с bytes source: version `F6F2AA4C3B4434A79AEB48729B77F0A54E694DFB18EBF42B1A9E134DFE56B776`, README `35CE8760A3C7922A4FF336A36B9DF0B9C1B63AC122796471A66F70EA11180999`, README_UA `00D94B5863BAC317F371DE8620B3FB2D409B9DB8910ACE08C8BD016D734F76AE`.
- Diff меняет только `VERSION = '0.3.0-dev.7'` на `VERSION = '0.3.0-dev.8'` и синхронные описания в двух README. Result SHA-256 совпадают с manifest: version `BA7A3A9F2CF5B7B1661165EE661A500F53AC05920AB2AF5B27D5C32D61F57520`, README `369D941EC37A5E13CC17374E6650EB270DDC7CF17E7D619492DD248B76354BAE`, README_UA `35B46B0BCCCC1D17F4EF3EA85B1DF0714AB55B34015530625E548829231146E7`.
- README корректно ограничивают invoice change: invoice currency включается в financial projection без orders/lots/procurement, пустой snapshot сохраняет EUR fallback. Они не заявляют изменение формул, policy, API, writes, browser/payment/DB/learning acceptance или production readiness.
- Оба README отдельно сохраняют PDF как неизменную памятку dev.7, установленный runtime как отдельный dev.7/d8 и dev.8 как candidate pending delivery. Это не подменяет отсутствие нового PDF generation/render evidence.
- AUTHOR_REPORT_RU.md (`69A7C98717721B239F4F440050769C81914A6356CEBA76A71DB1A509CB951468`) и MANIFEST.json (`F630AC441C24AC1B4AC5E95FB3EDBE14A730C1908351C91483019BB952ADEC7F`) согласованы с указанным scope и не выдают package за delivery или acceptance.

## Verdict

`ACCEPT_SCOPED_VERSIONED_METADATA_PACKAGE_ONLY`.

Допустимый следующий шаг root: атомарно интегрировать только эти пять проверенных package/evidence files на source `c00`/его документальном потомке, затем выполнить отдельный manifest/review и отдельную owner-local delivery процедуру при её точном допуске. Этот verdict не разрешает delivery, не повышает readiness и не переносит старые dev.7 runtime/browser evidence на dev.8.
