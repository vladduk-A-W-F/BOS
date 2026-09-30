# UXD01: первая проверка и исправление oracle

27.09.2026. Native exit 1, FAIL, попытка 1/3 сохранена. Новый ID или исправление harness не сбрасывают счётчик. Браузер, приложение и runtime не запускались.

Exact source 0338cc026a91f1aadc0f41ebf6cff812f72d7086; SHA256 cc97bee6d680df1bc4aedd6a3a6892b3283a17434867b268c11d38010b1732e7. Oracle v1 3466bde6b9e6dcd5d3d4a3f0ad40e976b5eb2780ac8150190c5e051824d64232, receipt 59a99c1579beb7fcb69552a2c86c7d1d8d2bf0ed6cf3e173c9f3167d4ca481da. Неизменённые файлы заморожены в qa/v1/.

Независимый bos3_candidate_review подтвердил: allStringLiterals (строки112-118) собирает StringLiteral, но обязательные dt подписи source5182 представлены JSXText. Assertion line216 падает до последующих проверок. Это доказанный дефект oracle, не доказанный дефект UI.

Узкая коррекция в той же карточке SAME-PROBLEM: автор bos3_crm_impl меняет только сбор подписей на trimmed direct JSXText из dt внутри единственного .bos-monitor-disclosure. Список десяти ожидаемых подписей, source pin, raw run1 и все прочие assertions сохраняются. Reviewer start_overview_review проверяет исправление и остальные ещё не выполненные assertions. Автор не один в проекте, canonical и продукт не редактирует.

Разрешение сейчас: исправление scratch oracle/scope без исполнения. Следующий запуск требует отдельного root назначения после review, без автоматического повтора. Первоначальное статическое одобрение oracle не обнаружило эту ошибку; оно не заменяет фактический FAIL.
