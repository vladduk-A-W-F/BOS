# BoS dev.8: incremental candidate/control integration review

Дата: 2026-09-28

## Scope

Проверены только documentary/control changes, которые подключают принятый dev.8 passport в D canonical, и статическое чтение selected-manifest consumer в `tools/bos_control.py`. Сам passport, product diff и QA не пересчитывались; CLI не запускался.

## Факты

- `CONTROL_STATE.json` согласует version `0.3.0-dev.8`, product `411e222c4687b6a029c027518d3f20453c5849db`, selected manifest `INVOICE_DEV8_CANDIDATE.json` и manifest SHA-256 `9286497d1aa88177fca6580b1ddcfabcd7345de9bb6eac19b4c7f170d3bacbb2`.
- Previous dev.7 package сохранён как historical record. Current runtime pins остаются `runtime_source_commit=d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`, `delivered_runtime_version=0.3.0-dev.7`; delivery dev.8 явно pending, `runtime_actions=0`.
- Верхние ACTIVE/TEAM записи помещают dev.8 package в completed state, delivery preparation отдельно в pending/final-pins state. Они не делают all16 migration dependency и не создают новый QA run.
- Candidate и control сохраняют `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`.
- `tools/bos_control.py:selected_candidate_manifest()` выбирает только safe JSON leaf из `docs/orchestration/bos3`. В `validate_bos3()` current consumer сравнивает product/version pins и false-readiness, но не обращается к `delivery_artifacts`. Следовательно, schema с `non_orchestration_runtime_delta` без `delivery_artifacts` совместима с этим read-only control consumer; это не означает delivery validation или application acceptance.

## Verdict

`ACCEPT_SCOPED_DEV8_CANDIDATE_CONTROL_INTEGRATION`.

Следующий допустимый шаг root: immutable manifest/documentary commit и отдельный final-pin review. Этот review не разрешает runtime action, не запускает CLI и не переносит dev.7 delivery evidence на dev.8.
