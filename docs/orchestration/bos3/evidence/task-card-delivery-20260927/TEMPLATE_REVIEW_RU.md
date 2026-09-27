# Dev.5 delivery: статическое принятие шаблона

27.09.2026. Автор bos3_fixture_impl; независимый start_overview_review.
Verdict: **ACCEPT_SCOPED_TEMPLATE_ONLY** после одного documentation P2.
0cdd3ef в README первоначально ошибочно был назван current canonical;
исправлен на historical dev4-template reference, не target/current pin.
Scripts не менялись. Imports/compile/tests/server/HTTP/DB executions: 0.

- maintenance_dev5_delivery.py:
  `d90c7519e8c2afbe62f437e8751464bd00ee8c802ab5a0619f479cd0f4e5ac54`;
- post_start_dev5.py:
  `d81041a8cc865d0c4c5f76f180c13adae2a6a9b3f7bd29f44dcea71338a63fd9`;
- исправленный README.md:
  `33c6678badc1f03c3f693fdb7a9454dba3940a78b684689a447297e7e7f34ed9`.

Fail-closed target/manifest pins=None и allowlist empty. Baseline только
installed e710/dev4. Сохранены source/prepared/database binding,
protected data/media/credentials digest, ready process identity и sole
loopback listener, official stop preflight до source switch. Post-start
лишь один future bounded GET без proxy/cookies/redirect/JS и exact HTML.
Ни миграции/seed/reset/rollback, ни вывода секретов. Старые окна не повторяются.

Следующий шаг только после принятого immutable candidate: root заполняет
exact target/manifest hash/allowlist, независимый reviewer проверяет эту
конкретную дельту и scope. Template verdict не разрешает исполнение.
