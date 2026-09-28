# Незалежний static review: B30-D control-home core source

Дата: 2026-09-28  
Режим: source-only review; imports, execution, state/ledger/lock reads і live transport не виконувалися.

## Перевірені exact inputs

| Артефакт | SHA-256 |
| --- | --- |
| `CORE_CARD.json` | `4e68f8ffdb4e1ffee20194501e708f250837dbeeefdbd6747769a78b13aacb37` |
| `CONTINUATION64_CONTROL_HOME_LOCK_CONTRACT_V2.json` | `1b526f468bc7e0d6da422da029eb8e81f1b91aaf0c7dd2229345327c4858193f` |
| `staged/bos_dev.py` | `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53` |
| `staged/codex_channel.py` | `eb3a758f985900f9ff83c588f071e1dd83b5d34de6b5a5a3eae1267b7ec27d28` |
| `MANIFEST.json` | `8a9f78b8876a20037b1ea073a2b0153bc3042a52aca5685c0fb4206ee4dcacad` |

## Підтверджене

- `resolve_control_home` у `staged/bos_dev.py:46` використовує fixed legacy `C:/Users/user/AppData/Local/BOSDev`, а не `LOCALAPPDATA`; неlegacy кандидати відмовляються до `mkdir`, state path чи lock.
- `state_lock` (`bos_dev.py:61`), `initialize` (`:156`) і `run` (`:173`) приймають/передають resolved `Path`; повторний виклик resolver з уже canonical `Path` є identity return, без нової filesystem canonicalization.
- CLI `main` каналу resolves `--home` до `AppTools` (`codex_channel.py:289` перед `:298`); `status` та `send` використовують цей самий `Path`. `deliver` resolves home до ledger path і `state_lock` (`:220`). Empty ledger не може легітимізувати nonlegacy home, бо resolver відмовляє раніше.
- Код не створює nonlegacy authority marker, config/queue/observer/ledger/lock set; nonlegacy state лишається явно непідготовленим. Це partial source preparation, не migration/cutover readiness.

## P1: direct delivery API може відкрити transport до відмови home

`codex_channel.deliver` отримує вже створений `client` (`codex_channel.py:220`) і викликає resolver до ledger/lock, але сам `AppTools` може бути створений прямим caller раніше (`AppTools` починається у `:65`). Лише CLI `main` гарантує resolver перед `with AppTools()` (`:289`, `:298`).

Це не створює nonlegacy ledger або directory, але порушує заявлений C64/card інваріант fail-closed **до AppTools startup** для selectable channel home та лишає direct API route без enforceable ordering. Мінімальне виправлення: або зробити public channel entrypoint таким, що отримує `home` і resolves його до створення `AppTools`, а delivery зробити internal тільки для вже-resolved home, або звузити/задокументувати API так, щоб зовнішній caller не міг передати pre-created `AppTools`; сам runtime contract має бути enforceable, не лише convention.

## Вердикт

`NOT_READY_STATIC_P1_DIRECT_APPTOOLS_BEFORE_HOME_REFUSAL`.

Інші перевірені core boundaries відповідають C64 V2 для inactive partial preparation. Після exact repair потрібен вузький independent delta review; dynamic tests, authority establishment, flow integration, cutover та будь-який runtime GO лишаються поза цією карткою.
