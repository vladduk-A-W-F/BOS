# Джерела конфігурації

Переглянуто 20.09.2026:
- https://developers.openai.com/de-DE/docs/config-file/config-reference : agents.enabled, max_concurrent_threads_per_session, default_subagent_model, per-role config_file.
- https://developers.openai.com/de-DE/docs/agent-configuration/subagents : project .codex/agents/*.toml, name, description, model, reasoning, sandbox, developer_instructions.

Англомовні URL без мовного префікса повертали 404; прочитані офіційні локалізовані сторінки. Моделі gpt-6-astra та gpt-5.6-terra присутні в доступних моделях цього Work-середовища; це не гарантія доступу в окремому акаунті/CLI. Статичний TOML parse не замінює перевірку завантаження конфігурації конкретною версією CLI. Акаунтна конфігурація не змінювалась.
