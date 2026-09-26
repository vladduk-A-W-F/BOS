# NETWORK-CI-CONTEXT-FIX

Підстава: NETWORK-CONTINUATION, власник «делай все этапы». Workflow run35516152992 на0975280 завершився failure до створення jobs; PG/browser сценарії не виконувалися. Причина в source: runner.temp недоступний у jobs.<job>.env за офіційною таблицею GitHub contexts. Початковий YAML/AST review не перевірив цю семантику.

Allowlist: .github/workflows/bos-network-targeted.yml, ця картка, evidence/network-acceptance/ci-context. Перенести лише дві змінні output у наявні always steps.env, передати наступним крокам через GITHUB_ENV. Зберегти token, branch/ref/repo/attempt guards, source SHA, harness, тайм-аути й artifact paths.

Автор pg_acceptance; незалежний reviewer integration_diagnosis. Root інтегрує після ACCEPT_SCOPED. Не називати цю картку новим бюджетом спроб: workflow invocation1 збережений, app invocations0. Наступний push — workflow invocation2 та перший фактичний запуск адресних PG/browser сценаріїв, якщо конфігурація прийнята. Ліміт3 не змінений. Readiness=false, pilot=false.
