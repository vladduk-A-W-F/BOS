# Канал Claude ↔ Codex

Постоянный draft PR «Канал Claude ↔ Codex». **Не сливать.** Правило — в AGENTS.md («Безшовний цикл за подіями»).

- Codex → Claude: `@claude перевір #<N> <short-sha>` после каждого PR или push; `@claude звіт: <до 5 рядків>` после доставки или блокера.
- Claude → Codex: `Команда Claude: <наступний крок>`; вердикты — в самих PR (`Рев'ю Claude: ACCEPT|CHANGES <sha>`).
- Codex выполняет последнюю `Команда Claude`. Изменения архитектуры, прав, схемы, секретов и AGENTS.md вливает только владелец.
- Чинне ТЗ: `docs/strategy/BOS_MONITORING_SPEC_UA.md` (BoS 4, картки M1–M9).
