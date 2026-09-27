# B30-UXD03-CARD-QA: одна адресная проверка

27.09.2026. Классификация: NEW_PRESENTATION_DELTA, новый pure
c01TaskCardFacts из author4999f7af9387488386729db02423460d9678bedf.
Не повтор fixture/training/progress/payment/membership/browser/full/PG/E2E.
Исторические caps не сброшены. Один запуск разрешён root после двух
независимых проверок: code bos3_candidate_review и harness
start_overview_review. Исполнитель bos3_crm_impl, не автор product code.

Точный source SHA-256:
`62e31d8f65879179d2b60124312c58fd848a3a252ef58737551adec3e57cc7fb`.
Oracle SHA-256:
`a3169b6b80ddb631b4ec0b9866472077326f0b69720e5301eee090c250c4d564`.
Scope SHA-256:
`35e3d94a9e75af7c156cc4f805090f9f35e819e3919069dad53d52647fec2751`.

Independent verdict: **READY_FOR_ONE_SCOPED_NODE_RUN**, attempt1/3
новой проблемы; сейчас допущена ровно одна попытка, не три запуска.
Исправленный parser извлекает ровно один text/babel body, удаляет только
штатные verbatim markers, парсит JSX без React transform и сохраняет
offsets body. Исходные expectations/fixtures не менялись; pre-run
rejection сохранён отдельно, попытка им не потреблена.

```powershell
& 'C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' 'D:/3/BOSDev/qa-scratch/bos3-uxd03-card-qa-20260927/uxd03_card_test.cjs' --source 'C:/Users/user/.codex/worktrees/bos3-product-design/repo/frontend/boss_app_source.html' --commit 4999f7af9387488386729db02423460d9678bedf --sha256 62e31d8f65879179d2b60124312c58fd848a3a252ef58737551adec3e57cc7fb
```

Сохранить exact argv/cwd, stdout/stderr/native exit, время, hashes.
Данные только в памяти. Не загружать приложение, не запускать build,
браузер, HTTP/network/DB и не трогать owner runtime. При первом FAIL
остановиться, сохранить результат; автоматический повтор запрещён.
Автор теста не принимает собственный результат: raw output идёт
независимому reviewer. Это не разрешение learning revision9: отдельный
owner exception всё ещё ожидается, ни среда ни прогон не созданы.
