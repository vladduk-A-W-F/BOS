# B30-UXD03-PREP: независимое принятие подготовки

Дата: 27.09.2026. Автор: существующий отдел дизайна, thread
01a0bffa-3fc7-7bc2-9868-86164c6e0315, завершённый turn
01a0e37d-ca24-7101-a9f9-e685f1ab4754. Независимый reviewer:
`/root/bos3_candidate_review`. Единственный интегратор: root.

## Источник и артефакты

- Clean detached source: `e710eb568717dfe3ede945feb899f030bd5ad1ab`,
  `C:/Users/user/.codex/worktrees/bos3-product-design/repo`.
- `UXD03_CONTRACT_RU.md`: SHA-256
  `0a8f0f64cc566db6d855d37d7905a7fa98be682a37527d7ea59a53355de7735e`.
- `HANDOFF.json`: SHA-256
  `c843ab9afb096801e79bf5d2ee87f8a4970893ffb4a7a13e9fae291329baaa96`.
- Исходный output: `D:/3/BOSDev/qa-scratch/bos3-uxd03-prep-20260927/`.
  Здесь сохранены точные копии без исправления авторского PENDING: итог
  независимого review находится в этом отдельном документе.

## Вердикт reviewer

`ACCEPT_SCOPED_DOCUMENTARY_PREPARATION`. P0-P2 findings не обнаружены.
Независимо сверены два artifact hashes, clean detached e710 и 10/10
входных delta hashes. Авторская карта включает 30 исходных файлов;
это статическая трассировка, не запуск продукта.

Подтверждено разделение:

- Настоящая очередь отдела существует: `department_id` фильтрует набор
  после `Policy.tasks()`, а не является новым правом или полем Task.
- Текущий исполнитель уже показан. `order_id/order_code` и handoff facts
  есть в list projection, но отсутствуют на компактной карточке.
- Подробности, история и источники используют существующие guarded
  маршруты; их нельзя безусловно объединять в карточке списка.
- Ожидание, его причина/участник и личное принятие не следуют из
  `handoff.current` и не реализованы текущими model/command semantics.

## Границы и следующий шаг

Подготовка завершена, UXD-03 как продуктовая возможность не принят.
Будущая отдельная UI-карточка может показывать существующие list-safe
факты только в `frontend/boss_app_source.html` и связанных стилях
`frontend/bos_design.css`, с обычными generated artifacts после
отдельного назначения. Такая карточка пока не назначена.

`UXD03-WAIT-01` остаётся предметом решения до waiting-функции: модель
состояния или dependency blocker, кто начинает/закрывает ожидание,
видимость, срок/просрочка, передача/завершение, audit/replay.
Backend/model/policy/routes/migrations/DB/runtime не менялись.
Build/test/browser/HTTP/DB runs: 0. Никакие лимиты не обнулены.
TECHNICAL_READY/PILOT_ALLOWED/MVP остаются false.

## Проверка интеграционной дельты

Тот же независимый reviewer отдельно проверил root diff трёх контрольных
записей и сохранённый evidence на documentation base
`f6caa6a23f29ad25ddfaec4f18ff167bb9533c22`:
`ACCEPT_SCOPED_CONTROL_INTEGRATION`, без P0-P2.
Копии совпадают с принятыми SHA; статус только
COMPLETED_SCOPED_DOCUMENTARY, implementation_authorized=false и
new_checks_authorized=0 сохранены. Product7018/runtimee710 неизменны;
historical dev3 entry не перенесён на dev4. NEEDS_OWNER_EXCEPTION
соответствует B30-12 revision9: фактический ответ, final manifest и
независимый pin-review предшествуют любому запуску.
