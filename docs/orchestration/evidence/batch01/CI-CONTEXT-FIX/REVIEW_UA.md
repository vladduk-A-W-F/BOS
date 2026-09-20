# CI: виправлення контексту runner

Незалежний reviewer bos_batch_review: ACCEPT_SCOPED_STATIC.
SHA256 workflow: `15103070570b00750948319fc2836337d0e58c45f29ffc9c896ee124d71ac742`.
BOS_BATCH_OUTPUT задано в чотирьох потрібних кроках, включно з mkdir; upload використовує той самий шлях. runner.temp дозволений у step env та with, але не job env.
Тригери, guards, refs, runner-команда, ліміти й склад тестів незмінні. Попередній run35503531221 відхилено до створення jobs; тести/PG не починалися. Це виправлення конфігурації до першого фактичного адресного прогону, не повтор full suite.

Джерело: https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability
