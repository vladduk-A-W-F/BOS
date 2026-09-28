# Независимый финальный review допуска focused QA

Verdict: **CHANGES_REQUIRED**. Допуск исполнения по проверенному admission не выдан. `executions=0`.

## Точные входы и граница

- Карточка: `FINAL_QA_REVIEW_CARD.json`, SHA256 `4d131a8655a901e690890294bd96541fde466e94d996ad31e5944a36672514dd`.
- Проверенный полный admission: `QA_ADMISSION.json`, SHA256 `7ebf336b9ce600855c240e0ea5ce4a5e46c1bfea5dcb2a8fb85dfba64f4d759e`.
- Runner: `run_focused_qa_once.py`, SHA256 `f75b6d682040cb4e02764959d3747c16182deacb1b7bc401d2bb5801ac5bb4ab`.
- Принятая source-only guard dependency: `QA_GUARD_REPAIR_REVIEW_RU.md`, SHA256 `0af287d575b0e09abc7424268b06ca89d22fe4e2323fab96dc37e7eb770caae4`.
- Consumer manifest: `consumers/MANIFEST.json`, SHA256 `3b684264bf6c3ae1825c8bbdd2ce9bd8e28e9618d1cdd04abd900f60a3253ec9`.
- Consumer tests: `97185036cb83f0ff7a72235b7785a28d2ddd3813275c0ae3cb136394e95c4a53`; legacy channel tests: `d93c6bc79f63aac6e020d4cab28fc856f3a31335492e69fb194c61cca86bcd66`.
- Reviewer: `/root/bos3_d_migration_review`, независим от авторов guard/admission и tests. Requested `gpt-6-astra/high`; observed `UNCONFIRMED`.
- Только чтение текста, сравнение текста, SHA256 и JSON evidence как данных. Код проекта, runner, imports, parser, compile и tests не запускались; live/process/resource/policy probes отсутствуют.

## Блокирующий Finding FQA-1 / P1

**Вложенные fixture-процессы authority suite не сохраняют source-bound изоляцию внешних групп.**

Точная проверенная версия `source/staged/test-control-home-authority.py` имела SHA256 `e150232e750b7e1af28861981eaaaf47dc25b147820a62741cc9852f2920dfe5`. Она сохранена автором без изменения bytes в [test-control-home-authority-before-child-isolation.py](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/test-control-home-authority-before-child-isolation.py:86); хеш сохраненной копии независимо сверен.

1. Строки 86 и 258 вызывают `subprocess.run(["cmd", "/c", "mklink", ...])`: executable не привязан к точному системному пути и отсутствует `/d`. Даже при разрешении настоящего системного cmd его обычный startup допускает выполнение Command Processor AutoRun до fixture-команды. Наличие AutoRun на этой машине не утверждается и не проверялось. Это не соответствует допуску только синтетических операций над scratch. `/d` отключает AutoRun согласно [документации Microsoft cmd](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd).
2. Строки 323 и 327 вызывают вложенный Python только с `-B`. Внешние `-I -S` не наследуются как параметры нового процесса. Поэтому startup нового Python допускает `site` и глобальные `.pth`/startup hooks до точного scratch loader, хотя provider затем загружается по явному пути. `PYTHONNOUSERSITE` не отключает весь `site`; `-B` лишь запрещает запись bytecode. См. [официальные параметры Python](https://docs.python.org/3/using/cmdline.html#cmdoption-S).

Минимальный ремонт: в обоих mklink вызовах использовать согласованный точный системный executable с `/d /c`; обоим lock child добавить `-I -S -B`, сохранив точные provider/path arguments, timeout и последовательность. Затем обновить evidence pointers и полный admission на новые bytes и получить отдельный независимый delta/pin verdict. Product source менять не требуется. Это не разрешение диагностики C64 и не разрешение повторить отвергнутую команду другим способом.

Root принял finding и передал ремонт исходному автору. Во время завершения этого отчета staged test уже изменился, но admission остался прежним `7ebf336b...`; новые bytes этим verdict не принимаются. Первоначальная проверка установила совпадение 13/13 pins на исходном наборе; после начатого ремонта это не является утверждением о совпадении текущего staged набора со старым admission.

## Принятые Части

**R1-T1 закрыт для указанных consumer test bytes.** Сравнение с `consumers/review-r1` подтвердило отключение автоматического TemporaryDirectory finalizer сразу после создания, проверку identity/containment/типов/reparse перед удалением и отказ с сохранением fixture при нарушении границы. Известный symlink удаляется только как конкретный leaf. Legacy channel использует тот же guarded cleanup в teardown и atexit; отказ дочерней очистки сохраняет также родительское дерево. Безусловного обходного finalizer/atexit удаления в проверенной версии не осталось. Это статический вывод, не результат теста.

**Guard delta принят статически.** Относительно сохраненного runner `69374d30a26b4782d1f0d44a9b70ba08972a65a9241477ccf4a8f7f0f968cd28` изменены только два удаления из GROUPS. Убраны `test_transferred_delivery_and_opaque_record_are_preserved` и `test_incomplete_relevant_record_refuses_without_send`. Неизменные ранее принятые G1/G2 участки повторно не переоценивались.

**Выбор методов согласован.** Admission и runner содержат одинаковые упорядоченные 13 authority + 9 consumer методов, всего 22. Оба direct group идут последовательно с fail-fast. CLI-self, прежний whole channel, EOF, wrapper static повтор и оба transition-specific SAME-PROBLEM ledger метода исключены. Нового бюджета из старых журналов не выведено; два ledger checks остаются `NOT_RUN`.

**One-shot и external gate корректно разделены.** Admission ограничивает ровно одним вызовом без auto retry. Startup/job/setup failure, SKIP-only, timeout и потеря receipt расходуют попытку. Source-only dependency не подменяет финальное принятие: root должен отдельно проверить внешний verdict, связывающий полный неизменный admission и runner. Текущий отчет такого принятия не дает; циклическая фиксация собственного хеша не требуется.

## Процессы, Лимиты И Evidence

- Два direct group процесса не означают два процесса всего. При полном прохождении выбранных authority tests ожидается максимум 13 setup cmd + 1 дополнительный cmd + 2 последовательных lock Python child, то есть до 16 дополнительных descendants и до 18 descendants всего, сверх самого guard. Ранний отказ уменьшает число. Эти children должны входить в ту же JobObject границу; их startup isolation является FQA-1.
- Ранее принятый guard использует общий 60-секундный test-wait budget, до 3 секунд ожидания direct-child после kill, raw files вместо PIPE и сохранение native evidence. Нет гарантии ограниченной задержки файловой системы и нет измеренного утверждения о доступной RAM. Итоговые raw/native evidence читаются после выхода guard и закрытия OS-owned JobObject.
- Исторические caps сохраняются. Переименование карточки, descendant или модели их не сбрасывает. Этот review не разрешает runtime/diagnostic/P05/full PG/E2E и не открывает заблокированные A09/A10/A11 маршруты.
- Installation authority владельца не равна отдельному C64 diagnostic authorization. C64, глобальная quiescence, миграционные receipts, phase-fault operation QA и ledger transition QA остаются отдельными незакрытыми условиями.
- `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`; installation/activation/full migration/QA PASS не установлены.

## Следующий Допустимый Шаг

Только завершить source-only FQA-1 repair и проверить узкий delta плюс точные обновленные pins/admission независимым reviewer. До отдельного `ACCEPT_EXACT_ONCE_SCOPED_QA_INVOCATION`, связанного с новым полным admission SHA256, root не запускает guard. Повтор уже принятых неизменных source reviews не нужен. После разрешенного вызова все равно потребуется отдельная проверка raw output; подготовленный тест не равен PASS.
