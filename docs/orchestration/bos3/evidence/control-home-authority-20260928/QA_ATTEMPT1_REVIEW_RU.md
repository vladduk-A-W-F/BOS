# Независимый review результата QA attempt 1

Verdict: **FAIL_SETUP / REMAINING_NOT_RUN / ATTEMPT_1_OF_1_CONSUMED_NO_RETRY**.

Однократный допуск израсходован. Raw evidence подтверждает отказ подготовки первого теста, а не проверенную регрессию продукта. Это result review, не новый execution gate. Reviewer executions=0.

## Проверенные Доказательства

| Файл | Независимо сверенный SHA256 |
| --- | --- |
| QA_FAILURE_REVIEW_CARD.json | `ad8217569ba520afa5a3946d795967a65193413b6d92ce4a603e15c6a5abd3e1` |
| ROOT_QA_NATIVE_RECEIPT.json | `bc4cb54b3c06b95c446d12801e9ea39578f1f258dbd0875257db6b4d0e71fdda` |
| qa-attempt1/RESULT.json | `c38b9725d57601cfacbd14c04c12885803e4428586da546f135ea324044fcc2a` |
| qa-attempt1/INVOKED.json | `f7b5f7b3c82aedd5ad44ed7aaa862e07701a1c780fc45aafe6ef89ffd7f0246c` |
| qa-attempt1/1-stdout.bin | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| qa-attempt1/1-stderr.bin | `b51b0899004f8c488562ce1095dfec5d1eecd467d71a67437eaf77041c802472` |
| QA_ADMISSION.json | `3f47365b8eb806f86a10c08c5b4a3598da3418b95045aed8c72af3d457800fd1` |
| FINAL_QA_ADMISSION_R2_REVIEW_RU.md | `9b495097393fa1c924e9aa50f215ffeb7b695e4aaf718995001bcc54da044fb8` |
| run_focused_qa_once.py | `f75b6d682040cb4e02764959d3747c16182deacb1b7bc401d2bb5801ac5bb4ab` |

Reviewer `/root/bos3_d_migration_review`, независим от root-оператора. Requested `gpt-6-astra/high`; observed `UNCONFIRMED`. Только raw/source reads, SHA256 и JSON evidence как данных. Tests/imports/parser/compile/replay/help/process-policy-resource probes/live actions: 0.

## Установленный Результат

1. Root receipt фиксирует native guard exit **2**, native tool chunk `17a48f`, wall time `0.6741068` секунды и `FAILED_OR_INCOMPLETE_STOPPED`. Reviewer читает сохраненный operator receipt; исходный tool event отдельно не воспроизводился. Guard RESULT и raw stderr согласованы с этим receipt.
2. RESULT содержит ровно одну запись группы: `source/staged/test-control-home-authority.py`, pinned Python с `-I -S -B`, 13 разрешенными selectors и `-v -f`. Native exit этой группы **1**. Consumer group отсутствует; в scratch evidence присутствуют только raw files группы 1.
3. [Raw stderr](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/qa-attempt1/1-stderr.bin) сообщает `Ran 1 test in 0.054s`, `FAILED (failures=1)`. Traceback указывает на [setUp, строка 88](D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928/source/staged/test-control-home-authority.py:88): `assertEqual(result.returncode, 0, result.stderr)`, фактически `1 != 0`, stderr fixture-команды: `The syntax of the command is incorrect.`
4. `Ran 1` означает один учтенный unittest case с отказом setUp, а не исполненное тело теста. Первое тело `test_active_default_alias_and_target_share_identity` не достигнуто. Прочие 12 authority methods и все 9 consumer methods: **NOT_RUN**. Завершенных test bodies: **0**. Часть scratch setup и source helpers до строки 88 выполнялась; это не считается отсутствием вообще любого выполнения source code.
5. Marker связывает invocation с точными принятыми admission/runner hashes. Все **13/13 current input pins** независимо совпали с admission и marker; значение `input_hashes_unchanged=true` дополнительно подтверждено чтением файлов, а не только принято из флага.
6. RESULT имеет `automatic_retry=false`, `application_checks=0`, `installation=false`, `phase_fault_qa=NOT_RUN`. Recorded elapsed guard interval `0.3289999999979045` секунды не является отдельной гарантией производительности. Timeout/termination path в этом запуске не проверен.

## Границы Вывода

Наблюдаемая причина остановки: ненулевой результат fixture mklink, превращенный assertion в setUp failure. Точная первопричина синтаксического отказа этим raw output **не доказана**. Нельзя из сообщения сделать вывод о junction permissions, Windows policy, неисправности product authority или подтвердить конкретное quoting/path объяснение. Автору разрешена отдельная статическая диагностика, не replay.

Guard остановил последовательность после первой неуспешной группы согласно записанному результату. Это не общий guard PASS: timeout, kill-race, resource limits и все аварийные ветви здесь не испытаны. `test_descendants_contained=true` соответствует успешному JobObject setup пути ранее проверенного guard; это не самостоятельный независимый процессный инвентарь. Процессные probes и проверка live quiescence не выполнялись.

По source path и trace можно установить запуск одной direct authority group и одной fixture cmd до отказа; lock children и consumer group не достигнуты. Это source-bound интерпретация, не измерение всех процессов ОС. Raw stdout пуст. Отдельное подтверждение состояния fixture filesystem после cleanup не собиралось; отсутствие дополнительной cleanup ошибки в stderr не заменяет такое подтверждение.

## Учет И Следующий Шаг

- **1/1 spent**, оставшихся разрешенных invocation нет. Startup/setup failure явно расходует попытку по admission. Предыдущее exact acceptance использовано, повторный запуск им не разрешен.
- `qa-attempt1` marker и raw evidence сохраняются. Не удалять marker, не менять ID/runner/инструмент для обхода бюджета и не делать автоматический повтор после ремонта fixture.
- Product source остается статически рассмотренным, но focused runtime QA не пройден. Два ранее исключенных SAME-PROBLEM ledger checks по-прежнему NOT_RUN; исторические caps не изменены.
- C64/live state/transport/installation не затрагиваются этим review. Phase-fault operation QA, глобальная quiescence и migration receipts остаются незакрытыми. TECHNICAL_READY=false, PILOT_ALLOWED=false.
- Следующий допустимый шаг: отдельная узкая source-only диагностика причины fixture отказа и отчет root. Данный документ не предоставляет новый execution budget или разрешение на установку. Любое будущее выполнение требует отдельного действительного основания в рамках исторических лимитов, не вывода разрешения из этой неудачи.

Чтения/хеш-проверки reviewer завершились exit 0; изменен только этот отчет. Никаких доказательств для product PASS или live migration acceptance не получено.
