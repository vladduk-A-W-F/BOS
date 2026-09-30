# B30-D-CONTROL-HOME-CHANNEL-TEST-SOURCE

## Зміна

Адаптовано ізольований синтетичний тестовий модуль до публічного API
`deliver(target, prompt, message_id, home=...)` з core source-only пакета.
Тестова функція `deliver` підміняє лише resolver, lock і конструктор `AppTools`, щоб
усі наявні ledger-assertions залишилися в тимчасовому каталозі й не створювали
реальний транспорт або live lock. `FakeClient` став контекстним менеджером, оскільки
публічний API тепер сам керує `with AppTools()`.

Додано окрему перевірку: реальний публічний resolver відхиляє неlegacy home
до виклику конструктора транспорту. Вона не підміняє `resolve_control_home`.

## Збережені межі

Залишено assertions для duplicate-id, content/new-id refusal, exact target і
prompt, UNCONFIRMED без resend, outside/self refusal та призначених targets.
`test_protocol_eof_fails_promptly` не змінювався: public API цієї перевірки не
стосується. Підміни не використовуються в окремому nonlegacy-refusal test.

Модуль імпортує тільки sibling `core/staged`, а не legacy live tools path.
Це inactive source-only зв'язування; воно не є cutover, runtime-активацією або
динамічним PASS.

## Залежності

- core channel: `3f1c4318a3693a47b088ca75742decbce84dda18942f97f039d424d392108a55`;
- core resolver/provider: `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`;
- interface: `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497`.

## Перевірка

Виконання, імпорт, компіляція, тест, transport, live state та мережа: `NOT_RUN`.
Наступний крок — незалежний статичний review цього source-only diff.
