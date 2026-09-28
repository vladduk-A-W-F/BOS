# B30-INVOICE-CURRENCY · авторский отчёт

## Точная база и дефект

База: `d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`; blob `erp/experience.py`: `181a45a66071858eb723d3d65e5facf488348b9c`.

`home(snapshot)` строил universe валют только из orders, lots и purchases. Поэтому invoice-only currency не попадала в `financial`, хотя расчёт receivable/paid уже читает invoices.

## Изменение

В существующий sorted universe добавлен `snapshot['invoices']`. Decimal-формулы, сортировка, fallback пустого набора в EUR, схемы и прочие проекции не менялись.

## Подготовленная regression

`erp/test_home_projection.py` содержит две pure-snapshot проверки: invoice-only USD с точными receivable и paid и нулями остальных полей; пустой snapshot сохраняет EUR fallback. `tests_not_run=true`; executions=0. Прежняя запись с `--keepdb` отозвана: она не является разрешением и не соответствует требованию не использовать существующую БД. Будущий runner ожидает отдельного isolated source-bound review; команды запуска пока нет.

## Границы

Не запускались tests, build, HTTP, browser, DB, payment commands, runtime, seed/migrate/reset, push или delivery. Это не acceptance и не меняет readiness. Следующий reviewer: `bos3_candidate_review`.
