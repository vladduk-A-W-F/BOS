# B30 dev8: bounded retry для atomic process receipt

Статус: `PREPARED_UNRUN_REVIEW_REQUIRED`. Это изолированная подготовка кода
по точному base `60f1e31fca6056711ea52d7aade6b65e0b14afff`; protected runtime
source, canonical tree и owner instance не изменялись. Никакой Python import,
тест, lifecycle, HTTP, ACL, data/media или секреты не выполнялись и не
читались.

## Изменение

В `scripts/bos3_local.py` изменён только `atomic_json`. После неизменённых
unique temp creation, JSON write, flush и fsync он вызывает `os.replace` до
трёх раз для того же самого temp-файла. Повтор допустим исключительно для
`PermissionError` с `winerror` `5`, `32` или `33`: первая попытка без паузы,
затем `50 ms` и `100 ms`, суммарно не более `150 ms`.

Любое иное исключение, `PermissionError` с иным Windows-кодом либо третий
применимый отказ немедленно пробрасывается. Успешный replace сразу возвращает
управление. Temp не пересоздаётся и на окончательной ошибке сохраняется, как
было ранее. Нет direct overwrite, ACL workaround, child/lifecycle повторов,
очистки либо иных refactor.

Новая чистая standard-library test-заготовка
`scripts/test_bos3_local_atomic.py` покрывает: одну успешную замену и exact
JSON; один симулированный `winerror=5` с успехом на том же temp; постоянный
`winerror=32` с тремя вызовами, старым target и diagnostic temp; отдельный
прямой сценарий `winerror=33`; не относящийся `OSError` и `winerror=87` без
retry. До fixture creation oracle проверяет каждый фиксированный ancestor от
`D:\\` до exact owned workspace через `lstat`: это должен быть directory без
symlink/reparse-point. `TemporaryDirectory` создаётся только непосредственно
в `D:\\3\\BOSDev\\qa-scratch\\bos3-atomic-receipt-repair-20260928`; cleanup
вызывается только для exact созданного child directory и проверяет его
исчезновение, не удаляя parent либо широкую D-path.

## Границы доказательства

Это robustness-изменение для наблюдаемого класса отказов, но не доказательство
того, что исторический `WinError 5` был transient, lock, reader, ACL или
каким-либо конкретным actor. Постоянный отказ остаётся failure, а не false
success. Тесты намеренно `UNRUN`; они не дают PASS до отдельной authorisation,
execution и независимого review raw evidence.

Счётчики не меняются: start window1 остаётся `1/1`, same problem `1/3`.
Ни retry, ни последующий lifecycle не разрешаются этой подготовкой. Следующий
разрешаемый этап -- независимый source/unrun-oracle review, затем отдельная
классификация root ровно одного isolated test либо будущего repaired-candidate
lifecycle window.

## Repair provenance

`REPAIR_STATIC_REVIEW_RU.md`
`4bc3c0b33bcbe25e77adc911023c6f5270183f19a22d6fa8540958535390b315`
принял source `6483cc...` и потребовал только P1/P2 repair test evidence.
До repair test SHA был `adbeb1...`, report SHA `a96e...`, manifest SHA
`bf27...`; полная история сохранена в `MANIFEST.json`. Source SHA остаётся
`6483cc...`; тесты по-прежнему `UNRUN`.
