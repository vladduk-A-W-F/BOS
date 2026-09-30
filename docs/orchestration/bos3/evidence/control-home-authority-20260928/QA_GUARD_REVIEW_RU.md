# Независимый source review QA guard

Вердикт: **CHANGES_REQUIRED**. Два actionable findings: G1/P1 timeout/pipe drain и G2/P2 отсутствие stop-on-first-method-failure. Runner не принят для final execution admission. Ни imports/tests, ни процессы для воспроизведения не запускались.

Дата: 2026-09-28. Карточка B30-D-CONTROL-HOME-FOCUSED-QA-GUARD-REVIEW. Автор runner: root. Reviewer: /root/bos3_d_migration_review. Requested gpt-6-astra/high; observed runtime UNCONFIRMED.

Точные independently verified inputs:

- QA_GUARD_REVIEW_CARD.json: `6785ebed2cc675fcd75335899807ce22d2cfcbd6369ecf0fc7f4fc91203bbad1`.
- run_focused_qa_once.py: `ad7ca7426aa3acbddc13746ebbc6e5b4adf1a986ee76efe2163d3228f4ba04d3`.
- Предыдущий source verdict: IMPLEMENTATION_REPAIR_R1_REVIEW_RU.md `21c32c1a7835002c55e2d14eec9bea269d29c36a02ed73a53f9b4d497868ac67`, ранее независимо создан и проверен этим reviewer; не переоценивался.
- QA scope: `25df441f261b91d646c20bb05c1856213336509a98731771859d2eb99e2a833f`, ранее проверенный proposal, не execution admission.

## G1 / P1: timeout может ждать потомка без ограничения

Места: run_focused_qa_once.py:176, :180; Job handle lifetime :117; RESULT запись :197.

На Windows `subprocess.run(capture_output=True, timeout=remaining)` после истечения timeout убивает прямого child, затем вызывает `communicate()` без нового timeout. Это видно в [исходнике CPython subprocess.run](https://raw.githubusercontent.com/python/cpython/3.11/Lib/subprocess.py). Если потомок удерживает унаследованный stdout/stderr pipe, исключение не вернётся guard до закрытия pipe. Job handle остаётся открыт, поэтому закрытие guard и KILL_ON_JOB_CLOSE также не наступают. Следовательно, внешний общий 60-second предел и достижение finally/RESULT не обеспечены этим механизмом. Это вывод по control flow, не результат локального воспроизведения и не утверждение о наблюдённой версии Python.

Raw output пока находится только в памяти subprocess.run и записывается после его возврата. Поэтому тот же отказ лишает попытку raw logs и final native receipt; сохранится лишь INVOKED marker.

Минимальное направление ремонта: открыть exact create-new stdout/stderr log files до spawn, писать child streams прямо в них и использовать явно bounded ожидание owned child без pipe-drain communicate. Timeout/kill/wait операции должны иметь ограничение и честно сохранять неизвестный native exit. После durable result guard может завершиться, закрывая собственный anonymous job и оставшихся потомков. Либо использовать другой точный reviewed mechanism, который завершает только owned job descendants и оставляет recorder живым. Нельзя просто закрыть/terminate текущий self-assigned job до записи evidence: guard входит в него. Нельзя подменять это global kill/process scan.

## G2 / P2: методы продолжаются после первого падения

Место: run_focused_qa_once.py:172; остановка на :186 проверяет только итог whole-group exit.

Args передают `-v`, но не `-f`. Обычный unittest продолжает оставшиеся методы группы после error/failure; второй group не запустится, однако обещанный stop-on-first-failure внутри первого group не выполнен. Это особенно существенно для единственной разрешённой попытки с адресным разбором ошибок. [Документация unittest --failfast](https://docs.python.org/3/library/unittest.html#command-line-options) определяет нужное поведение.

Минимальный ремонт: добавить `-f`/`--failfast` каждому direct test-script invocation. После ошибки не запускать другие методы/группы автоматически; raw verbose output должен различать attempted/completed/skipped и не представлять всю выбранную группу выполненной.

## Method selection и классификация

Текстом проверены все 24 выбранных имени: 15 AuthorityTests и 9 ConsumerAuthorityTests; 24/24 объявлены в соответствующих тестовых исходниках. Это **до двух sequential child group invocations**, а не 24 child process запуска. Раздельные `-I -S -B` interpreters сохраняют нужную module-cache изоляцию suites.

Исключения реализованы в GROUPS: CLI-self, wrapper source-text repeat и полный legacy channel suite не выбраны; нет EOF, C64, storage inventory, app/runtime/lifecycle и operation phase-fault tests.

NEW scope по предмету: authority phase/receipt/alias/lock identity и acquisition generation, provider origin/fallback/cache/hardlink/reparse, consumer authority/output refusal. Два authority метода `test_transferred_delivery_and_opaque_record_are_preserved` и `test_incomplete_relevant_record_refuses_without_send` проверяют именно новый путь перенесённого ledger, но остаются transition-specific SAME-PROBLEM в части прежних channel semantics. Они не получают новый исторический channel budget только из названия suite. Root должен привязать их к problem-specific attempt accounting в final admission.

Exit 0 правильно обозначается NATIVE_ZERO_REQUIRES_INDEPENDENT_OUTPUT_REVIEW и не повышает готовность. SKIP останется в verbose output и требует отдельного разбора; в частности, необязательная возможность создать provider file symlink не превращается в доказанный provider-reparse PASS.

## Job containment и граница полномочий

Функция создаёт anonymous job с NULL security attributes, то есть handle не наследуется; ассоциирует только GetCurrentProcess до test children. Нет поиска, открытия или помещения в job посторонних существующих процессов. Ошибка создания/назначения останавливает путь без fallback. Эти свойства согласуются с [CreateJobObjectW](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-createjobobjectw).

Порядок ctypes fields соответствует [BASIC_LIMIT_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) и [EXTENDED_LIMIT_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information); 0x2000 обозначает KILL_ON_JOB_CLOSE. Это статическое сопоставление, не проверка ABI/совместимости текущего host.

CreateProcess descendants обычно включаются в job; закрытие последнего handle с этим flag завершает связанные процессы. [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) описывает также nested-job ограничения. Guard не задаёт breakaway flags, но реальная возможность assignment здесь не наблюдалась и не объявляется успешной заранее. Ошибка assignment должна остаться terminal evidence этой попытки.

Использование нового job только для guard и создаваемых им tests относится к предложенному QA containment, не является C64 server/listener diagnostic и не разрешает policy changes, C64 retry или наблюдение других процессов. Одобрение source не заменяет execution admission.

## Остальные проверки и финальные gates

- Input checks ограничивают dependency paths scratch root, отвергают `..`, reparse и non-single-link files; required pins включают оба tests и фактически нужные core/consumer providers. Финальные consumer test bytes пока изменяются отдельно, поэтому текущий review не принимает их будущий hash.
- Fixed OUTPUT, mkdir без exist_ok и create-new/fsync INVOKED до children препятствуют автоматическому повтору после уже начатой попытки. Существующий attempt directory не удаляется. Неудача до/после marker остаётся фактом root accounting; отсутствие RESULT не разрешает повтор.
- Guard сверяет review reference только по path/hash. Наличие файла, включая source-only review, само по себе не является execution verdict. Для final invocation root должен получить отдельное независимое принятие exact admission/runner/pins/methods/attempt references и проверить этот exact admission hash до вызова; текущий QA_GUARD_REVIEW не подходит как такое разрешение.
- После G1/G2 нужны source rereview изменённых bytes, закрытый R1-T1 cleanup guard, final immutable test pins и отдельно подготовленный admission. Operation phase-fault coverage и live quiescence не входят в этот focused run и остаются pending.
- Primary API документы использованы как справка по механизму. Они не доказывают состояние текущего Windows, Python, policy, процессов или ресурсов.

Выполнены static reads/hashes и текстовое сопоставление method names, exit 0. Дополнительно прочитаны публичные первичные API docs и исходник CPython; локальный код не импортировался и не парсился как программа. Создан только этот review-файл. Runner, source, consumers, admission и карточки reviewer не менял; commit не создавался.

executions=0; probes=0; live_state_reads=0; transport=0; installation=0; QA_PASS=false; TECHNICAL_READY=false; PILOT_ALLOWED=false.

Следующий шаг: root исправляет G1/G2 в своём runner, возвращает exact diff этому independent reviewer; подготовка final admission продолжается после закрытия cleanup dependency. Этот verdict не разрешает запуск.
