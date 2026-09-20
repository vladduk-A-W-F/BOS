# NETWORK-ACCEPT-CI · один новий адресний hosted стенд

Дозвіл: NETWORK-CONTINUATION, власник «делай все этапы». Runtime після незалежно прийнятого NETWORK-PLAN-CURRENCY: c15dfe0e3aeefde2fd4fa7af0e9dd2c7c04072a59b185554b821576b4c2111ca; product commit f00a2faf10ebcc4bc120b34f7d15d9bf889fa491.

Allowlist: .github/ci/network_pg.py, .github/ci/network_browser_acceptance.py, .github/workflows/bos-network-targeted.yml, ця картка/evidence. PG автор pg_acceptance, reviewer integration_diagnosis. Browser автор browser_acceptance, reviewer currency_completion. Root інтегрує; source review дозволяє один запуск, але не є виконаним PG/browser PASS.

Умови: тільки repository vladduk-A-W-F/BOS, push у feat/network-operations-20260920, перша спроба, точний standalone commit token [bos-network-acceptance:20260920-01], changed CI allowlist, clean checkout, exact commit/source SHA. Timeout12хв PG/15хв browser; жодних автоматичних rerun. Два PG concurrency methods з live pg_blocking_pids і третім з’єднанням. Браузер — тільки наявний Chrome нового hosted runner; немає browser install/download fallback. Дані/media ізольовані synthetic, очищення підтверджується; source DB canaries незмінні. Артефакти з raw logs/screenshots/SHA-index після успіху чи відмови.

Це не full historical suite/E2E, не A09/A10/A11 повтор, не Windows/physical-device acceptance, не production activation. Browser lost-response injection, live permission-revocation race та RFQ creation UI не входять у цей обмежений прогін; старі backend/Node докази збережені лише у власному scope. TECHNICAL_READY=false, PILOT_ALLOWED=false. Фінальний статус визначити за фактичними receipts та незалежним оглядом, не за exit status без доказів.
