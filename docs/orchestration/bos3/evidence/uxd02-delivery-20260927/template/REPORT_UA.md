# UXD02-DELIVERY-PREP

## Призначення

Статична fail-closed підготовка одного майбутнього ordinary owner-local delivery
від встановленого dev6 до ще не призначеного dev7. Вона є новим candidate
planning window і не повторює спожиті f55 entry, UXD01 dev6 delivery, навчальні
перевірки або їхні historical caps.

## Зафіксована база

- Runtime baseline: `8114097b3ddf2c31b709ed945bfb514c404ce4f1`
  (`0.3.0-dev.6`).
- Попередній delivery manifest для цієї бази:
  `PROVENANCE_DEV6_CANDIDATE.json`, SHA-256
  `8488451db588dc414c5ec12c9fed1efc98b72072897f35317e288fc4761a549c`.
- Dev7 candidate SHA, manifest path, manifest SHA-256 та immutable file
  allowlist: `PENDING`.

Обидва скрипти містять `None` для candidate/manifest pins та порожній
`DELIVERY_FILES`; будь-які capture, apply або post-start дії відмовляються,
доки root не внесе разом independently reviewed immutable values.

## Збережені guardrails

- Exact baseline/source digest, clean checkout, prepared SQLite binding і
  protected DB/media/owner-access/runtime-secret aggregate.
- Identity-bound process receipt, loopback-only listener, official stopped
  preflight та унікальний archive namespace `UXD02-DELIVERY`.
- Exact candidate ancestry, manifest blob SHA-256, product file allowlist та
  PNG signature, якщо єдиний дозволений static PNG входить у diff.
- П'ять одноразових етапів залишаються зовнішньою official lifecycle
  послідовністю: capture, stop, apply, start, receipt-only post-start. Скрипти
  не запускають init, seed, migrate, reset, rollback, start або stop і не
  мають automatic retry.
- Post-start допускає лише один bounded `127.0.0.1:8030/` GET без proxy,
  cookies чи redirects, після майбутнього authorized start; exact HTML
  звіряється з committed template та однією підстановкою `0.3.0-dev.7`.

## Межі та наступний крок

У цій підготовці не виконувалися import, compile, tests, CLI, HTTP, DB,
process або runtime операції. Вона не змінює canonical source, product,
manifest, readiness, доступи чи secrets. Спочатку потрібні завершені UI QA,
versioned pack, immutable manifest/candidate і незалежний static review
`start_overview_review`; лише тоді root виконує окремий final-pin binding та
вирішує delivery.
