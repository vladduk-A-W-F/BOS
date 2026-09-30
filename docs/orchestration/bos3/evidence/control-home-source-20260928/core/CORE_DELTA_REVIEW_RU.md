# Незалежний delta review: direct channel API repair

Дата: 2026-09-28  
Режим: лише static source review; imports, AppTools, state/ledger reads і sends не виконувалися.

## Exact delta inputs

| Артефакт | SHA-256 |
| --- | --- |
| `staged/bos_dev.py` | `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53` |
| `staged/codex_channel.py` | `3f1c4318a3693a47b088ca75742decbce84dda18942f97f039d424d392108a55` |
| `INTERFACE.json` | `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497` |
| `REPORT_RU.md` | `5a5319a7452c8045d2a6ae49e466f90917704be25bb2f81a1b3f325806009cc4` |
| `MANIFEST.json` | `7952f641f0e7ca7a52ba93a93b4cc601c78b6a3df660299b44c66c563dd5aefa` |

## P1 closure

Public `deliver(target, prompt, message_id, home=...)` тепер виконує `resolve_control_home(home)` до створення `AppTools`. Його body перенесено в `_deliver_resolved(client, ..., home)`, який отримує вже canonical Path. CLI зберігає той самий порядок: resolves `--home` перед єдиним `AppTools` startup, після чого `send` викликає лише private resolved path.

Таким чином selectable nonlegacy home відмовляється до transport, ledger path, lock або directory creation через підтримуваний public API. Manifest, interface та report узгоджено описують intentional signature break і межу сумісності.

Private helper технічно залишається доступним Python module attribute, але він не є public contract. Неінтегровані зовнішні callers із pre-created `AppTools` не можуть вважатися виправленими цим source-only patch; їхня сумісність і міграція потребують окремої exact card. Це не є обхід fail-closed public path.

## Вердикт

`ACCEPT_SCOPED_STATIC_CORE_DIRECT_API_REPAIR`.

P1 із `CORE_STATIC_REVIEW_RU.md` закрито для declared public API. Результат лишається inactive partial preparation: authority establishment, `bos_flow` integration, full cutover, dynamic tests і runtime activation не прийняті та не дозволені.
