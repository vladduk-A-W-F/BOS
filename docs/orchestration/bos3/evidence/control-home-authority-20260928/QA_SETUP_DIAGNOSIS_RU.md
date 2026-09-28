# QA setup: статический диагноз первого отказа

Карточка `B30-D-CONTROL-HOME-QA-SETUP-DIAGNOSIS`. Режим: только чтение; новых
запусков, импортов, parser/compile и правок source не было. QA1/1 израсходован;
этот документ не разрешает повтор и не является PASS.

## Установленные факты

- Замороженный тест `source/staged/test-control-home-authority.py` имеет SHA-256
  `6bab3caeaa6a77c179b57c7813fe3707d44e915818e3a77e3252d6571f63c518`.
  Первый `setUp` на строках 86-88 вызывает `subprocess.run` со списком
  `C:/Windows/System32/cmd.exe`, `/d`, `/c`, `mklink`, `/J`, затем два
  синтетических пути `self.alias` и `self.home`.
- `qa-attempt1/RESULT.json` SHA-256
  `c38b9725d57601cfacbd14c04c12885803e4428586da546f135ea324044fcc2a`
  фиксирует native exit 1, `application_checks=0`, consumer `NOT_RUN` и
  `FAILED_OR_INCOMPLETE_STOPPED` без автоматического повтора.
- `qa-attempt1/1-stderr.bin` SHA-256
  `b51b0899004f8c488562ce1095dfec5d1eecd467d71a67437eaf77041c802472`
  показывает один `FAIL` в `setUp` на строке 88: `result.returncode` равен 1,
  `result.stderr` содержит `The syntax of the command is incorrect.` Один
  test method был начат, но его body не выполнялся. stdout пуст.

## Интерпретация

[Microsoft `mklink`](https://learn.microsoft.com/windows-server/administration/windows-commands/mklink)
определяет синтаксис `mklink /j <link> <target>`; порядок аргументов в source
ему соответствует. [Microsoft `cmd`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd)
определяет `/d` как отключение AutoRun и `/c` как исполнение следующего
`<string>` со специальной обработкой кавычек. [Python `subprocess`](https://docs.python.org/3/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows)
на Windows преобразует список аргументов в одну строку по правилам C runtime.
Следовательно, стык сериализации Python и разбора `cmd /c` является
обоснованной гипотезой для синтаксического отказа. Это **не доказанная
первопричина**: raw evidence не содержит фактическую строку CreateProcess,
конкретные имена временных путей либо разбор `mklink` по токенам.

Также не доказаны состояние command extensions, точная форма временных
путей и то, какое звено выдало сообщение. Поэтому невозможно честно закрепить
однострочный corrective diff или утверждать, что дополнительные кавычки
исправят запуск. При отдельном разрешённом диагностическом шаге сначала
нужно получить exact non-secret argv/serialized command line и два synthetic
path, затем независимому reviewer сверить quoting для `cmd /c` и только после
этого оценить минимальную правку. Текущий лимит QA не допускает replay.

Отказ произошёл в тестовом создании junction. Он не проверил resolver,
physical lock, ledger, consumers или миграцию и не доказывает дефект
продуктового core. Источник и manifest не изменены; независимый reviewer
отдельно рассматривает raw результат.
