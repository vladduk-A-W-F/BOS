# C01 · доручення, відповідальні та результат

Локальну реалізацію0.2.14-dev перевірено й погоджено у зазначених межах. Це не приймання всього MVP. Full25 complete=false, exit1 через відкриті умови; усі наявні локальні перевірки поза відомим A09 без нових регресій.

## Що працює

Доручення має EmployeeFK, optionalSalesOrderFK, строк, пріоритет, текст результату й історію автора/причини/попередніх значень. Створення, редагування, завершення, архів і відновлення проходять попередній перегляд та окреме погодження. RawREST/admin bypass закрито. Архів не входить в активніKPI; overdue визначається одним календарним правилом. No-change не створює proposal абоAudit.

Історичні assignee/status/result/FK не переписуються. Міграція додає nullableполя, зберігає старі ID/rows/high-water. Повтор відкриття завершеного доручення зберігає старий результат; нове завершення потребує явного підтвердження. Джерела в історії перевіряються за поточними правами навіть після відв’язування.

Завершення роботи не означає оплату чи відвантаження; їхні факти залишаються у відповідних ERP джерелах. Інструкція — docs/TASKS_UA.md.

## Фактичні докази

- Final scoped backend55/55; controlledTask UI40перевірок плюс12independent wire probes, exact build/source preservation. Це не браузер.
- Full25 SQLite:151функціональна+5launcher+543Django,5×1000інваріантів. Доступ:8928HTTP+9redirects/57fieldtests та12C01controls(104HTTP).
- Concurrency:104methods/110ERPpairs/33ERPactions,0skip; одночасні Task/Employee/джерельні зміни під actual mutex.
- Native restore16/16: exact53таблиці; Task4,6receipts/history й усі старі B03/B02 джерела збережені після нової інсталяції.
- Gate8: 30/31; відомий ConnectionResetError для13MiB. PostgreSQL/Windows/CI не запущені; gate6/9/10 у цій збірці відсутні. A09лімітспроб не поновлювався; activation/browser blockers незмінні.
- SourceSHA 9ddc3320083042df6c5353e655812d27a35993935f474a9cdba1d3a7330a061e; rawreportSHA 5b0237fbaa6bed9dec542658373327dd813823c4304114edc9d8022db7c89748. Код і дві вихідні БД незмінні протягом full25.

## Збережені red та мінімальні виправлення

Full24 наsource1ece101a виявив старий буквальний ref уcheck_original і два historical fixtures, які залишали tasks на новому leaf. В обох targets додано tasks0004: всі29testmethods/94assertions literal unchanged. check_original зберіг старі32checks,3додаткові перевіряються окремо; verify/countcontract незмінний. Actual32+3 і2/2 пройшли до повторногоfull25. Незалежні огляди погодили exactfiles; rawred не видалено.

Earlier rootnative1 мав setup-orderred: Tasks після B03whole snapshot. Поправлено лише порядокpopulateTasks→populateCorrections; старі14assertions/повнийsnapshot не звужено, native2іfull25 пройшли16/16. Детальні джерела — INTEGRATION_SHA256.json, compatibility/, backend/, ui/, restore/ та обидва verifyreports.

## Незалежний консенсус і межі

Фінальний scoped review, historical-targets review та legacy-source review збережені поряд із exactSHA. Виправлення dayfingerprint/reopen/result/malformedID та source403/404 закриті. Нових локальних блокерів C01 у виконаних перевірках немає. UI browser/PG/Windows і загальний паспорт релізу не прийняті. Далі — C03, який до цього commit існував тільки в окремих tmpкандидатах.
