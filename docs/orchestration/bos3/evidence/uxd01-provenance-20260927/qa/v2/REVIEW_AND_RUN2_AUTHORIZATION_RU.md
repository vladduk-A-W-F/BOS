# Исправленный AST oracle: review и один адресный запуск

27.09.2026. Независимый start_overview_review: ACCEPTED_FOR_ONE_FOCUSED_RETRY. Проверены exact harness fc43cf5bbb0fd49912dfdb7f40f5af47c0cd535425238562fbcda15cf00d7b6b, scope 6ea974f4222caa84f7f2e198f464c6ef3381996e2d0e406566a7da5cd6a34a61, report 5969d800bd5a745b9ac08541a0bbfdb4ae767e434fe99eea9e979e54adabf6ab.

Изменён только сбор trimmed direct JSXText в dt внутри единственного .bos-monitor-disclosure. Десять labels, pins и остальные assertions сохранены; reviewer отдельно проверил применимость ранее не достигнутых assertions. Исходный FAIL1/3 остаётся в qa/v1.

Root разрешает исполнителю bos3_crm_impl ровно одну попытку2/3 в той же проблеме после подтверждённой коррекции oracle. Команда bundled Node с тем же source0338cc026a91f1aadc0f41ebf6cff812f72d7086 и SHA cc97bee6d680df1bc4aedd6a3a6892b3283a17434867b268c11d38010b1732e7; scratch v2 path прежний. Повтор pin guards необходим для нового запуска, а не повтор успешного продуктового теста.

Только AST/file/Git, отдельные run2 raw stdout/stderr, native exit и receipt. Не исполнять приложение/браузер/HTTP/БД/build/уроки/ERP/CRM. Никакого автоматического повтора. После запуска независимый reviewer проверяет raw evidence, root решает интеграцию. Этот допуск не обнуляет исторические лимиты и не является browser/runtime/full acceptance.
