# NETWORK-PG-RUNNER-FIX

Підстава: run35516516284, PG16.15 підключено, але worker завершився до виконання тестів: DiscoverRunner.run_tests() потребує test_labels. Source/canary незмінні, disposable cleanup підтверджено. Це дефект harness, не доведений дефект бізнес-операцій.

Allowlist: .github/ci/network_pg.py, ця картка, відповідні evidence. Мінімальна правка: run_tests([]). ExactRunner.build_suite явно складає лише два зафіксовані methods і не делегує discovery; тести та assertions не змінюються. Автор pg_acceptance, reviewer integration_diagnosis.

Історія зберігається: один workflow validation failure, один worker invocation із TypeError, нуль PG test methods. Наступне виконання — після незалежного review, разом із виправленим browser harness; без широкого suite, зміни runtime або readiness.
