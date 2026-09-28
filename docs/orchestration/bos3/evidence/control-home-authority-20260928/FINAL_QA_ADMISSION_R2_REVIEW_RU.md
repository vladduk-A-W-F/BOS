# Final QA Admission R2: независимый delta review

Verdict: **ACCEPT_EXACT_ONCE_SCOPED_QA_INVOCATION**.

Принят ровно один root-operated вызов точного scoped QA guard по полному неизменному admission ниже. Это независимое принятие допуска, не результат тестов, не полномочие на установку и не product readiness. Reviewer executions=0.

## Exact Binding

| Артефакт | SHA256 |
| --- | --- |
| FINAL_QA_REVIEW_R2_CARD.json | `447fbfd89846c4968a283c2d984ead7d5fe7286455141bf94b9e92d72f4a3948` |
| QA_ADMISSION.json, полный файл | `3f47365b8eb806f86a10c08c5b4a3598da3418b95045aed8c72af3d457800fd1` |
| run_focused_qa_once.py | `f75b6d682040cb4e02764959d3747c16182deacb1b7bc401d2bb5801ac5bb4ab` |
| source/staged/test-control-home-authority.py | `6bab3caeaa6a77c179b57c7813fe3707d44e915818e3a77e3252d6571f63c518` |
| source/MANIFEST.json | `00997c1323aaf7b8927f7c36ffbd341b422695402fc925012f9a8ff74e03598c` |
| source/REPORT_RU.md | `861cbafdcae28e28dbbef7af8a682a0d6a9c1e7270440ef49409071a2f4bbb11` |
| consumers/MANIFEST.json | `3b684264bf6c3ae1825c8bbdd2ce9bd8e28e9618d1cdd04abd900f60a3253ec9` |
| FINAL_QA_ADMISSION_REVIEW_RU.md, предыдущее решение | `6d7381266e9f1cd306f5c73768dd64d6a602169beed96dd8cae503c906d9c16b` |
| QA_GUARD_REPAIR_REVIEW_RU.md, source-only dependency | `0af287d575b0e09abc7424268b06ca89d22fe4e2323fab96dc37e7eb770caae4` |

Reviewer `/root/bos3_d_migration_review`, независим от авторов test, guard и admission. Requested `gpt-6-astra/high`, observed `UNCONFIRMED`. База `00607be24a608e481efa4437408e7b338fcafe93`. Единственная запись reviewer: этот отчет.

## FQA-1 Закрыт

Текстовый diff точного authority test относительно сохраненной версии `e150232e750b7e1af28861981eaaaf47dc25b147820a62741cc9852f2920dfe5` содержит только четыре замены:

- [Строка 86](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/staged/test-control-home-authority.py:86) и строка 258: `C:/Windows/System32/cmd.exe /d /c` вместо bare `cmd /c`. PATH lookup и Command Processor AutoRun исключены этими argv. Наличие/отсутствие AutoRun не исследовалось.
- [Строка 323](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/staged/test-control-home-authority.py:323) и строка 327: вложенный Python теперь получает `-I -S -B`. Startup isolation задана непосредственно каждому child; точный provider, scratch paths, timeout, stdout assertions и последовательность не изменены.

Изменение решает оба конкретных пути выхода за source-bound startup scope. Новых findings в этом delta нет. Native cmd и Python не запускались reviewer; никаких диагностических probes для закрытия finding не требуется и не выполнено.

## Pin И Admission Проверка

Все 13/13 файлов из `QA_ADMISSION.json.pins` независимо пересчитаны и совпадают с полными значениями admission, включая неизменные accepted product source, оба cleanup test файла, wrapper files и manifests. Полный admission hash и runner hash независимо совпали с карточкой. Source manifest изменяет test pointer и добавляет provenance ремонта, не меняя product pins.

Diff admission относительно `QA_ADMISSION_REJECTED_FQA1.json` (`7ebf336b9ce600855c240e0ea5ce4a5e46c1bfea5dcb2a8fb85dfba64f4d759e`) содержит только новый authority test hash, новый source manifest hash и имя внешнего отчета `FINAL_QA_ADMISSION_R2_REVIEW_RU.md`. Иные scope/budget/argv/gates изменения отсутствуют.

Прежние принятия сохранены по неизменным bytes: R1-T1 cleanup включая finalizer/atexit; guard G1/G2; narrowed 13 authority + 9 consumer methods; один общий 60-секундный test-wait budget и до 3 секунд direct-child teardown wait; raw files и native receipt; JobObject только guard и его descendants. Повторный model review неизменного кода не выполнялся.

## Неподвижные Условия Допуска

- Только root, один вызов, без auto retry, по точным admission/runner/pins. Любой drift отменяет этот exact acceptance. Root проверяет этот внешний verdict и его привязку до вызова; source-only review dependency не заменяет эту проверку.
- 22 выбранных метода, два direct group последовательно. До 16 дополнительных fixture descendants: 13 setup cmd, один дополнительный cmd и два последовательных lock Python child. Итого до 18 descendants сверх guard; early failure уменьшает фактическое число. Это не разрешение исследовать существующие процессы.
- Startup/job/setup failure, SKIP-only, timeout, lost receipt и native error расходуют единственную попытку. Одноразовый marker не удаляется и не переиспользуется. Существование/готовность live state этим review не проверялись.
- Общий test timeout не является гарантией bounded filesystem latency. Raw/native evidence окончательно читать после guard exit и OS cleanup JobObject; затем нужен отдельный независимый raw-output review. Статическое принятие не означает runtime PASS.
- Два transition-specific SAME-PROBLEM ledger метода остаются NOT_RUN. CLI-self, whole channel, EOF и wrapper static повтор не включены. Нового бюджета из исторических логов не выведено. Все прежние caps и A09/A10/A11 действуют.
- C64 diagnostic authorization не получен и не подразумевается; отвергнутые policy/server/port probes не разрешены. Installation authority владельца не подменяется этим scoped QA verdict.
- Phase-fault operation QA, ledger transition QA, глобальная quiescence, migration receipts и installation/activation остаются отдельными gates. TECHNICAL_READY=false, PILOT_ALLOWED=false; full migration/QA PASS не установлен.

## Выполненная Проверка

Только чтение текста, SHA256, текстовые diff и JSON evidence как данных. Hash/read commands завершились с exit 0; `git diff --no-index` вернул ожидаемый exit 1, показывающий перечисленные изменения. Tests/imports/parser/compile/runner/process probes/live actions: 0. Следующий разрешенный шаг: root выполняет ровно принятый scoped вызов, сохраняет native/raw evidence и передает их на независимый review без автоматического повтора.
