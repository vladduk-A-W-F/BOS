# Независимый delta review QA guard

Вердикт: **ACCEPT_GUARD_SOURCE_FOR_FINAL_ADMISSION_PREPARATION**. G1/P1 и G2/P2 закрыты в текущем exact source. Новых actionable regressions в узком diff не обнаружено. Execution admission этим review не выдан.

Дата: 2026-09-28. Карточка B30-D-CONTROL-HOME-FOCUSED-QA-GUARD-REVIEW-R2. Автор root; независимый reviewer /root/bos3_d_migration_review. Requested gpt-6-astra/high; observed runtime UNCONFIRMED.

## Проверенные pins

| Вход | SHA-256 |
| --- | --- |
| QA_GUARD_REPAIR_REVIEW_CARD.json | 326f279234ed2e2507579819ce8df3858963871df341dc60ec2223bdebccb71f |
| run_focused_qa_once.py | 69374d30a26b4782d1f0d44a9b70ba08972a65a9241477ccf4a8f7f0f968cd28 |
| run_focused_qa_once_review1.py | ad7ca7426aa3acbddc13746ebbc6e5b4adf1a986ee76efe2163d3228f4ba04d3 |
| QA_GUARD_REVIEW_RU.md | 2202336075d1b64a9ca55288c1505c5cf30e92924de00e32ac41246b32a5e0ae |

Все четыре SHA независимо вычислены и совпали. Проверен actual text diff current против сохранённого original. Неизменные GROUPS, admission checks, path checks и JobObject setup повторно не оценивались; прежние статические выводы и ограничения сохраняются.

## G1: CLOSED

В run_focused_qa_once.py:175 stdout/stderr файлы создаются exclusive до Popen. Child получает прямые file handles, stdin=DEVNULL, close_fds=True. `capture_output`, PIPE и `communicate` из изменённого пути удалены; прежний бесконечный pipe-drain после timeout здесь отсутствует.

Строка 181 ограничивает wait остатком общего test budget. При timeout строки 186-190 обращаются только к созданному child и ограничивают дополнительное ожидание тремя секундами. Неизвестный native exit сохраняется как неизвестный. Строка 196 прекращает группы по самому факту TIMEOUT, поэтому гонка с native exit 0 не превращает timeout в успех.

Raw файлы flush/fsync выполняются в finally. RESULT по прежнему записывается create-new с fsync; anonymous job handle удерживается до OS teardown guard. Доступа к посторонним процессам или fallback диагностики diff не добавляет.

Принята именно граница shared 60-second test wait budget плюс до трёх секунд дополнительного owned-child wait. Не заявляется жёсткая верхняя граница filesystem/API latency. При неопределённом termination потомки могут дописать raw файлы до фактического выхода guard и закрытия job, поэтому окончательные raw/native evidence проверяются только после подтверждённого native guard exit. До этого RESULT не доказывает, что job уже закрыт. Неполное evidence после аварии остаётся INCOMPLETE и не разрешает retry.

## G2: CLOSED

Строка 172 добавляет `-f` обоим direct unittest invocations. Первый error/failure останавливает методы текущей группы, а nonzero exit или timeout останавливает дальнейшие группы. Прежний `-v` сохраняет подробный raw output. SKIP не становится failure автоматически и по прежнему требует независимого разбирательства; exit 0 не повышает готовность.

## Scope и последующий admission

Этот source pin всё ещё содержит прежние 15 authority + 9 consumer methods в двух отдельных sequential interpreters. Root сообщил о намерении убрать два transition-specific SAME-PROBLEM ledger метода из-за неустановленного доступного исторического бюджета. На момент этого review такое сокращение не входило в проверенный diff.

Консервативное исключение этих методов не сбрасывает историю и не доказывает ledger transition QA. После удаления entries нужны новый runner hash и final exact admission review уже для 13+9; текущий verdict не переносится на изменённые bytes автоматически. Ledger transition evidence остаётся NOT_RUN отдельным gate. Старые 8/10/11 channel logs не являются разрешением на новый запуск.

До выполнения обязательны: принятый final cleanup delta consumer tests, immutable source/test pins, точный admission с independently accepted execution scope и problem-specific attempt accounting, проверка exact admission/runner hash перед единственной invocation. Наличие source-review файла или его digest не заменяет execution verdict. Operation phase-fault QA, live quiescence, C64 exception и installation gates не меняются.

Выполнены только статические reads, hashes и text diff. Hash/read commands: exit 0; diff показал ожидаемые изменения G1/G2. В объединённой read-команде финальный exit 0 относится к завершившему чтению, не к запуску тестов. Создан только этот allowlisted review-файл. Runner, consumers, source, карточки и admission reviewer не изменял; commit не создавался.

executions=0; probes=0; imports=0; live_state_reads=0; transport=0; install=0; QA_PASS=false; TECHNICAL_READY=false; PILOT_ALLOWED=false.

Следующий шаг root: подготовить указанное сужение GROUPS и финальный exact admission после cleanup acceptance, затем передать их на отдельный независимый review без выполнения.
