# GPT/Codex · перевірка конфігурації

20.09.2026. Проєктні TOML файли мають дев’ять ролей; ліміт одночасних субагентів — чотири, канонічні зміни інтегрує root. Для складної координації/архітектури/review задано gpt-6-astra, для реалізації — gpt-5.6-terra. Поточна сесія делегує реальні задачі штатними засобами; самі TOML не створюють постійний фоновий сервіс.

Назви моделей і параметри agents.enabled, agents.max_concurrent_threads_per_session, default_subagent_model, default_subagent_reasoning_effort та agents.<name>.config_file звірено з відкритими офіційними сторінками:

- [Models](https://learn.chatgpt.com/docs/models)
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)

Проєктні файли у .codex/agents мають name, description і developer_instructions. Локальний inspector перевіряє TOML, залежності карток, ролі та незмінність 11 GATES. Codex CLI у цій середовищі відсутній; завантаження конфігурації зовнішнім CLI не запускалось. Доступ конкретного облікового запису до моделей не виводиться з документації. Продуктовий OpenAI API не ввімкнено; він має окремий контракт даних і бюджету.
