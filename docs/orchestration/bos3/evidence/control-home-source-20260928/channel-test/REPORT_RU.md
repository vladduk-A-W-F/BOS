# B30-D-CONTROL-HOME-CHANNEL-TEST-SOURCE

## Зміна

Адаптовано ізольований синтетичний тестовий модуль до публічного API
`deliver(target, prompt, message_id, home=...)` з core source-only пакета.
Тестова функція `deliver` підміняє лише resolver, lock і конструктор `AppTools`, щоб
ledger-assertions залишилися в тимчасовому каталозі й не створювали
реальний транспорт або live lock. `FakeClient` став контекстним менеджером, оскільки
публічний API тепер сам керує `with AppTools()`.

Після першого статичного review тест прив'язано до виправленого
`core-target-guard/staged/codex_channel.py`. Для outside та всіх self targets
тест викликає публічний `deliver()` з legacy константою і непідміненим
`resolve_control_home`, перевіряє `ChannelError` і `AppTools.assert_not_called()`.
Окрема перевірка nonlegacy home також залишає публічний resolver непідміненим
і перевіряє відмову до створення транспорту. Після другого статичного review
виправлено тип `assertRaises`: `ControlHomeError` імпортується безпосередньо
з того самого staged `bos_dev.py`, де його визначено. Ці refusal cases не читають
ledger або live home.

## Збережені межі

Залишено assertions для duplicate-id, content/new-id refusal, exact target і
prompt, UNCONFIRMED без resend, outside/self refusal та призначених targets.
`test_protocol_eof_fails_promptly` не змінювався: public API цієї перевірки не
стосується. Тестові підміни resolver/lock обмежені ledger fixtures.

Модуль імпортує тільки sibling `core-target-guard/staged`, а не legacy live tools path.
Це inactive source-only зв'язування; воно не є cutover, runtime-активацією або
динамічним PASS.

## Залежності

- revised test source: `3cdcbd99aaa2133f6283c73b51bc80fcc1add3b9a992c3fa83e567931a25b1b1`;
- prior focused test source: `77c37be60b2a71c71c245f75fbfeb6b23e537eafe56cdb2d904c56d18efb7e92`;
- previous test draft: `c1b6f8ddc695dad2b56f27ad1540e89791793f8b95e97d546f83558a2f91809c`;
- core channel: `371a02a413477de65186adcb53cfdf7d99c428b1c4dea81eef77494fe76f9235`;
- core resolver/provider: `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`;
- interface: `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497`;
- guard review: `6ab166a62c57ffaf7ca8a0092402451b795a8dfe35bfa13685d4a820771ac203`;
- initial test review: `0ed0aaf9edd57e710bedd362aa33089c1a60f1add04f813d67c77a0f97de096b`;
- focused test review: `a8db7ea5c6e2074b2a27decfd54008268ddd8b6b251feb21e7439e8888ad6ebb`.

Guard/evidence вже інтегровано як archival commit
`e7b3fbf1ad42d061be6dd9965ba7dfd6d53f311c`. Author-card base
`86334504ff6d56f2a8442141b3d2a36b435ebb89` належить config-only
контексту; product runtime цим тестовим джерелом не змінено.

## Перевірка

Виконання, імпорт, компіляція, тест, transport, live state та мережа: `NOT_RUN`
(exit codes відсутні, executions=0). Перевірено лише текстову відповідність
allowlist і SHA-256 файлів. Наступний крок — незалежний статичний review
цього source-only diff; reviewer verdict поки відсутній.
