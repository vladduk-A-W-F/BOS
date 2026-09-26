# REVIEW-MEMBERSHIP-PREVIEW-REUSE

Пріоритет P1. Модуль: Membership UI. Власник `bos_frontend`. Статус **ON_HOLD_OWNER_REVIEW**. Залежність: нове явне рішення власника після `FREEZE_FOR_OWNER_REVIEW`.

## Проблема та доказ

Membership UI actual3 на private source `b5ab…` має загальний verdict **FAIL: 7 PASS / 1 FAIL / 0 NOT_RUN**. Невдала перевірка показала другий mocked preview; повторний запис `Employee` не доведений. Private v5 `4c21…` має лише static acceptance, `behavior=NOT_RUN`, shared apply 0. Отже виправлення не інтегроване й поведінково не прийняте.

## Дозволений scope після відновлення робіт

- `frontend/boss_app_source.html`;
- `assets/app.js` лише як відтворюваний build output;
- один точно визначений membership evidence/contract у `docs/orchestration/evidence/**`;
- ця картка та відповідний модульний звіт.

Інші модулі, БД, production, Sites, ролі та доступи поза scope.

## Наступний крок

1. Відтворити точний мінімальний diff private v5 або заново сформувати еквівалентний diff з видимим source SHA.
2. Незалежно перевірити, що повторне підтвердження використовує вже отриманий preview/token і не створює другий preview.
3. Виконувати поведінкову перевірку лише за окремим authorization із зафіксованим лімітом; static review не рахувати як behavior PASS.

## Критерій результату

Source/build digest збігаються; exact membership scenario має PASS, другий preview відсутній, один confirm прив’язаний до першого preview, побічних записів немає; незалежний reviewer підтверджує commit, scope, середовище й raw receipt. До цього статус залишається `ON_HOLD_OWNER_REVIEW`.
