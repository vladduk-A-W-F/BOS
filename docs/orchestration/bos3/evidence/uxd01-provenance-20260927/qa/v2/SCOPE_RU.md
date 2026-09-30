# UXD01-PROVENANCE-QA: межа AST-oracle

## Призначення

`NEW_AST_PRESENTATION_DISCLOSURE`. Це одна вузька перевірка фінального
presentation-delta: п'ять показників загального моніторингу мають
структурно зв'язані джерело, спосіб розрахунку, межі охоплення, часові
застереження та дозволений перехід до розділу.

Це не browser/E2E, не перевірка fixture, прогресу навчання, HTTP, БД,
прав доступу або повного frontend suite. Історичні ліміти інших проблем
та попередні QA-спроби не змінюються.

## Ціль і пін

- Файл: `frontend/boss_app_source.html`.
- Commit: `0338cc026a91f1aadc0f41ebf6cff812f72d7086`.
- Повний SHA-256: `cc97bee6d680df1bc4aedd6a3a6892b3283a17434867b268c11d38010b1732e7`.
- Вихідний контракт: canonical
  `docs/orchestration/bos3/evidence/uxd01-provenance-20260927/SOURCE_CONTRACT_RU.md`,
  SHA-256 `8a98780e1a6c4c846b83460f566d52c498105090ff8994d23a8a9afb8a4a81c5`.

Перед будь-яким майбутнім запуском harness перевіряє чисте дерево цільового
checkout, точний HEAD і SHA-256 повного вихідного файлу. Інша ревізія або
незбережена зміна є `STOP`, а не підстава послабити oracle.

## Oracle

1. AST читає тільки один `<script type="text/babel">`; застосовує ті самі
   одноразові вилучення Django `verbatim`, що й локальний build script, та
   парсить тільки його тіло Babel без трансформації JSX.
2. У `BoSHome` повинні бути чотири нефінансові descriptor-и (`orders`,
   `jobs`, `quality`, `tasks`) із погодженими destination section/sub та
   provenance (`source`, `calculation`, `scope`, `branch`, `period`,
   `deviation`, `action`). П'ятий `receivable` має лишатися під
   `bosCan('finance')` і вести лише до `erp/costs`.
3. `BosGlobalMonitor` повинен мати умовно відображені лише при `ready`
   provenance details: джерело, розрахунок, охоплення, філіальний caveat,
   period caveat, бізнес-дату, час читання, відсутність часу оновлення
   джерел, відхилення й наступний крок. Це перевіряє змістовні labels і
   AST-зв'язок з `businessDate`, `at`, `readTime`, а не повний текст картки.
4. Перехід метрики лишається disabled без `ready` або `metric.allowed`, а
   callback додатково вимагає `canUse()` і `available(section, sub)`.
   При неготовому стані замість details має бути non-trusted empty disclosure.
5. Єдиний select моніторингу є вибором валюти; це не підтверджує і не
   створює філіальний фільтр. Oracle не оцінює серверне Policy enforcement.

## Заборонене під час майбутнього запуску

Не дозволені React mount/render, DOM, browser, application import, build,
компіляція production assets, HTTP, БД, мережа та повний suite. Harness
використовує лише Node stdlib, `assets/babel.js` як parser і читання Git
metadata цільового checkout.

## Допуск

Спроба `1/3` завершилась `exit 1` через дефект collector-а oracle: він
шукав rendered labels як Babel `StringLiteral`, хоча вони є прямими
`JSXText` у `dt`. Це не є результатом UI-інваріанта. Версію v1, run1 і їхні
hashes root заморозив у canonical evidence
`uxd01-provenance-20260927/qa/v1`.

Ця v2 корекція звужено бере trimmed direct `JSXText` лише з `dt` усередині
єдиного `.bos-monitor-disclosure`. Вона не збирає глобальний JSXText,
не змінює expected labels, source pins або інші assertions. Перед будь-якою
спробою `2/3` потрібні незалежний verdict `start_overview_review` для exact
harness і окремий явний дозвіл root. Відмова, hash mismatch або FAIL не
допускають автоматичного повтору.
